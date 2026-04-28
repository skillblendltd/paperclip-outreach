"""process_call_queue — picks pending CallTask rows whose `scheduled_for`
has elapsed, builds a fully-rendered CallPrompt, dispatches via the
provider-agnostic call_provider boundary, and writes a CallLog audit row.

Run via cron every 5 minutes:
    */5 * * * * python manage.py process_call_queue

Idempotency: each task transitions through pending → dispatched → done.
Re-running the cron tick on an already-dispatched task is a no-op.

A task that fails 5 dispatch attempts is marked `failed` with skip_reason.
"""
from __future__ import annotations

import logging
import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from campaigns.models import CallLog, CallTask
from campaigns.services import channel_timing

logger = logging.getLogger(__name__)


MAX_ATTEMPTS = 5
INTER_CALL_SLEEP_SECONDS = 30   # rate-limit consecutive dispatches


class Command(BaseCommand):
    help = 'Dispatch eligible CallTask rows via the configured call provider.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit', type=int, default=20,
            help='Max tasks to dispatch in one run (default 20)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Pick eligible tasks but do not dispatch.',
        )
        parser.add_argument(
            '--provider', type=str, default='vapi',
            help='Override provider slug (default vapi).',
        )
        parser.add_argument(
            '--task-id', type=str, default='',
            help='Process exactly one task by ID (testing).',
        )

    def handle(self, *args, **options):
        limit = options.get('limit') or 20
        dry_run = options.get('dry_run', False)
        provider_slug = options.get('provider') or 'vapi'
        single_id = options.get('task_id') or ''

        now = timezone.now()
        if single_id:
            qs = CallTask.objects.filter(id=single_id)
        else:
            qs = CallTask.objects.filter(
                status='pending', scheduled_for__lte=now,
            ).order_by('scheduled_for')[:limit]

        tasks = list(qs)
        if not tasks:
            self.stdout.write('No call tasks ready for dispatch.')
            return

        self.stdout.write(f'Picked {len(tasks)} task(s) for dispatch.')

        dispatched = 0
        skipped = 0
        failed = 0

        for idx, task in enumerate(tasks):
            prospect = task.prospect
            label = f'{prospect.email or prospect.phone} ({prospect.business_name or ""})'

            # Late-stage re-checks. State may have drifted since enqueue:
            # prospect could be opted out, phone could be cleared, or an
            # operator could have called manually.
            skip_reason = self._late_check_skip_reason(prospect)
            if skip_reason:
                self._mark_skipped(task, skip_reason)
                skipped += 1
                self.stdout.write(self.style.WARNING(
                    f'  SKIP {label} — {skip_reason}'
                ))
                continue

            if dry_run:
                self.stdout.write(f'  [DRY RUN] would dispatch {label}')
                dispatched += 1
                continue

            ok, err = self._dispatch(task, provider_slug)
            if ok:
                dispatched += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  DISPATCHED {label} — call_id={task.provider_call_id}'
                ))
            else:
                if task.attempts >= MAX_ATTEMPTS:
                    self._mark_failed(task, err)
                    failed += 1
                    self.stdout.write(self.style.ERROR(
                        f'  FAILED (max attempts) {label} — {err[:120]}'
                    ))
                else:
                    self.stdout.write(self.style.ERROR(
                        f'  RETRY-LATER {label} — {err[:120]} '
                        f'(attempt {task.attempts}/{MAX_ATTEMPTS})'
                    ))

            # Rate-limit between dispatches
            if idx < len(tasks) - 1 and not dry_run:
                time.sleep(INTER_CALL_SLEEP_SECONDS)

        self.stdout.write(
            f'\nDone. dispatched={dispatched} skipped={skipped} failed={failed}'
        )

    # ------------------------------------------------------------------
    # Dispatch helpers
    # ------------------------------------------------------------------

    def _late_check_skip_reason(self, prospect) -> str:
        """Re-check eligibility at dispatch time; state can drift since enqueue."""
        if not getattr(prospect, 'phone', ''):
            return 'prospect_phone_cleared'
        if not getattr(prospect, 'send_enabled', True):
            return 'send_disabled'
        if getattr(prospect, 'status', '') in {
            'opted_out', 'not_interested', 'customer', 'design_partner',
        }:
            return f'terminal_status:{prospect.status}'

        # Channel-timing recheck — important so we don't spam if the prospect
        # received a fresh email between enqueue and dispatch.
        ok, why = channel_timing.can_place_call(prospect)
        if not ok:
            return f'timing:{why}'
        return ''

    def _dispatch(self, task: CallTask, provider_slug: str) -> tuple[bool, str]:
        """Build the prompt, call the provider, write the CallLog row.
        Returns (success, error_message). Atomic on the task transition."""
        from campaigns.call_provider import base as cp_base
        from campaigns.services.prompt_builder import build_call_prompt

        prospect = task.prospect

        try:
            prompt = build_call_prompt(prospect, correlation_id=str(task.id))
        except Exception as exc:
            logger.exception('process_call_queue: prompt build failed task=%s', task.id)
            with transaction.atomic():
                task.attempts += 1
                task.skip_reason = f'prompt_build_error: {exc}'[:1000]
                task.save(update_fields=['attempts', 'skip_reason', 'updated_at'])
            return False, str(exc)

        try:
            result = cp_base.place(prospect, prompt, provider_slug=provider_slug)
        except Exception as exc:
            logger.exception('process_call_queue: provider dispatch crashed task=%s', task.id)
            with transaction.atomic():
                task.attempts += 1
                task.skip_reason = f'provider_crash: {exc}'[:1000]
                task.save(update_fields=['attempts', 'skip_reason', 'updated_at'])
            return False, str(exc)

        if not result.success:
            with transaction.atomic():
                task.attempts += 1
                task.skip_reason = f'provider_error: {result.error}'[:1000]
                task.save(update_fields=['attempts', 'skip_reason', 'updated_at'])
            return False, result.error

        # Success — write CallLog and flip task to dispatched.
        now = timezone.now()
        with transaction.atomic():
            campaign = getattr(prospect, 'campaign', None)
            CallLog.objects.create(
                campaign=campaign,
                prospect=prospect,
                phone_number=prospect.phone,
                vapi_call_id=result.provider_call_id,  # Vapi-named field, but the value is provider-agnostic
                status='placed',
                triggered_by='process_call_queue',
            )
            prospect.calls_sent = (prospect.calls_sent or 0) + 1
            prospect.last_called_at = now
            prospect.save(update_fields=['calls_sent', 'last_called_at', 'updated_at'])

            task.status = 'dispatched'
            task.attempts += 1
            task.dispatched_at = now
            task.provider_call_id = result.provider_call_id
            task.skip_reason = ''
            task.save(update_fields=[
                'status', 'attempts', 'dispatched_at', 'provider_call_id',
                'skip_reason', 'updated_at',
            ])
        return True, ''

    def _mark_skipped(self, task: CallTask, reason: str) -> None:
        task.status = 'skipped'
        task.skip_reason = reason[:1000]
        task.save(update_fields=['status', 'skip_reason', 'updated_at'])

    def _mark_failed(self, task: CallTask, error: str) -> None:
        task.status = 'failed'
        task.skip_reason = error[:1000]
        task.save(update_fields=['status', 'skip_reason', 'updated_at'])
