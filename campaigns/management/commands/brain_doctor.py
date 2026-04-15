"""Sprint 7 Phase 7.1.8 — brain_doctor.

Lints every active ProductBrain nightly (or on demand) and reports
missing / suspicious / drift issues. Non-destructive — never writes to
the DB. Exit code 1 if any CRITICAL finding, 0 otherwise.

Run manually:
    python manage.py brain_doctor
    python manage.py brain_doctor --strict  # non-zero exit on CRITICAL

Nightly cron wiring comes after Phase 7.3 observation proves brains
are stable.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

from django.core.management.base import BaseCommand

from campaigns.models import Campaign, PromptTemplate, ProductBrain


REQUIRED_JOB_KEYS = ('reply', 'call_opener', 'classify', 'transcript_insight')
REQUIRED_BRAIN_FIELDS = (
    'sequence_rules', 'timing_rules', 'terminal_states',
    'escalation_rules', 'success_signals', 'call_eligibility',
    'content_strategy', 'jobs',
)


class Command(BaseCommand):
    help = 'Lint every active ProductBrain and report issues.'

    def add_arguments(self, parser):
        parser.add_argument('--strict', action='store_true',
                            help='Exit 1 if any CRITICAL finding')
        parser.add_argument('--skip-cli-ping', action='store_true',
                            help='Skip the Claude CLI auth healthcheck (for offline runs)')
        parser.add_argument('--skip-log-scan', action='store_true',
                            help='Skip the reply monitor log failure-streak scan')

    def handle(self, *args, **opts):
        findings = []  # (severity, brain_slug, message)

        # 0a. Claude CLI auth healthcheck.
        # Added 2026-04-15 after local cron silently produced 461 "exit 1"
        # failures over 2 days because the OAuth access token had expired
        # and the CLI was not auto-refreshing in -p non-interactive mode.
        # brain_doctor now catches this on every run. Skip with --skip-cli-ping
        # when running offline or in environments where CLI auth is irrelevant.
        if not opts.get('skip_cli_ping'):
            self._check_cli_auth(findings)

        # 0b. Reply monitor log failure-streak scan.
        # Surfaces "Claude exited with code N" spikes in the last hour so
        # credential expiry, rate limits, or prompt-size blowups get caught
        # before the inbound backlog grows silently.
        if not opts.get('skip_log_scan'):
            self._check_reply_log(findings)

        brains = ProductBrain.objects.select_related('product', 'reply_prompt_template') \
                                     .filter(is_active=True)

        for pb in brains:
            slug = pb.product.slug

            # 1. Required fields present (non-empty)
            for field_name in REQUIRED_BRAIN_FIELDS:
                val = getattr(pb, field_name, None)
                if val is None:
                    findings.append(('CRITICAL', slug, f'{field_name} is None'))
                elif field_name == 'terminal_states' and not val:
                    findings.append(('WARN', slug, 'terminal_states is empty'))
                elif field_name == 'jobs' and not val:
                    findings.append(('WARN', slug, 'jobs is empty (defaults will apply)'))

            # 2. Jobs dict has all required keys with a model
            jobs = pb.jobs or {}
            for jk in REQUIRED_JOB_KEYS:
                if jk not in jobs:
                    findings.append(('INFO', slug, f'jobs.{jk} missing (defaults to sonnet 4.6)'))
                elif not jobs[jk].get('model'):
                    findings.append(('WARN', slug, f'jobs.{jk} has no model'))

            # 3. sequence_rules references statuses that make sense
            seq = pb.sequence_rules or {}
            if 'new' not in seq:
                findings.append(('WARN', slug, 'sequence_rules has no "new" entry (seq 1 untriggered)'))

            # 4. Voice row wired
            if not pb.reply_prompt_template_id:
                findings.append(('CRITICAL', slug, 'reply_prompt_template not set'))
            else:
                pt = pb.reply_prompt_template
                if not pt.is_active:
                    findings.append(('CRITICAL', slug, f'reply_prompt_template "{pt.name}" is inactive'))
                if pt.feature != 'email_reply':
                    findings.append(('WARN', slug, f'reply_prompt_template feature={pt.feature} (expected email_reply)'))

            # 5. Overrides reference real brain fields only
            overrides = Campaign.objects.filter(
                product_ref=pb.product,
            ).values_list('brain_override__overrides', flat=True)
            for o in overrides:
                if not o:
                    continue
                for key in o.keys():
                    if key not in REQUIRED_BRAIN_FIELDS:
                        findings.append((
                            'WARN', slug,
                            f'campaign override key "{key}" does not match any ProductBrain field'
                        ))

        # 6. Campaigns with use_context_assembler=True but no brain
        flagged = Campaign.objects.filter(use_context_assembler=True).select_related('product_ref')
        for c in flagged:
            if not ProductBrain.objects.filter(product=c.product_ref, is_active=True).exists():
                findings.append((
                    'CRITICAL',
                    c.product_ref.slug if c.product_ref else '?',
                    f'Campaign "{c.name}" has use_context_assembler=True but no active brain',
                ))

        # Report
        if not findings:
            self.stdout.write(self.style.SUCCESS('All brains clean.'))
            return

        criticals = [f for f in findings if f[0] == 'CRITICAL']
        warns = [f for f in findings if f[0] == 'WARN']
        infos = [f for f in findings if f[0] == 'INFO']

        for sev, slug, msg in findings:
            style = {
                'CRITICAL': self.style.ERROR,
                'WARN':     self.style.WARNING,
                'INFO':     lambda s: s,
            }[sev]
            self.stdout.write(style(f'[{sev}] {slug}: {msg}'))

        self.stdout.write('')
        self.stdout.write(f'Summary: {len(criticals)} critical, {len(warns)} warn, {len(infos)} info')

        if criticals and opts.get('strict'):
            sys.exit(1)

    # ------------------------------------------------------------------
    # Ops healthchecks added 2026-04-15
    # ------------------------------------------------------------------

    def _check_cli_auth(self, findings):
        """Probe `claude` CLI auth with a minimal one-shot prompt.

        Raises a CRITICAL finding on:
          - CLI binary missing
          - Non-zero exit (likely 401 auth error)
          - Output contains 'authentication_error' / 'Invalid authentication'
          - Access token in /root/.claude/.credentials.json expires in <24h
            (so we warn BEFORE breakage, not after)
        """
        slug = 'cli_auth'

        # Static check: credentials file exists + expiry lookahead
        cred_paths = [
            Path('/root/.claude/.credentials.json'),
            Path(os.path.expanduser('~/.claude/.credentials.json')),
        ]
        cred_path = next((p for p in cred_paths if p.exists()), None)
        if cred_path is None:
            findings.append(('WARN', slug, 'no .credentials.json found on either /root or $HOME path'))
        else:
            try:
                data = json.loads(cred_path.read_text())
                oauth = data.get('claudeAiOauth') or {}
                expires_at_ms = oauth.get('expiresAt')
                if expires_at_ms:
                    expires = datetime.fromtimestamp(expires_at_ms / 1000, tz=dt_timezone.utc)
                    now = datetime.now(dt_timezone.utc)
                    hours_left = (expires - now).total_seconds() / 3600
                    if hours_left < 0:
                        findings.append((
                            'CRITICAL', slug,
                            f'OAuth access token EXPIRED {abs(hours_left):.1f}h ago. '
                            f'Run: docker exec -it outreach_cron claude setup-token'
                        ))
                    elif hours_left < 24:
                        findings.append((
                            'WARN', slug,
                            f'OAuth access token expires in {hours_left:.1f}h. '
                            f'Refresh preemptively: docker exec -it outreach_cron claude setup-token'
                        ))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                findings.append(('WARN', slug, f'could not parse {cred_path}: {exc}'))

        # Live probe: one-shot ping
        try:
            t0 = time.time()
            result = subprocess.run(
                ['claude', '--model', 'sonnet',
                 '--max-turns', '1',
                 '--output-format', 'text',
                 '-p', 'Reply with the single word: pong'],
                capture_output=True, text=True, timeout=45,
                cwd=os.getenv('PAPERCLIP_REPO_DIR', '/app'),
            )
            elapsed = time.time() - t0
            out = (result.stdout or '') + '\n' + (result.stderr or '')
            if result.returncode != 0:
                findings.append((
                    'CRITICAL', slug,
                    f'claude -p returned exit {result.returncode} in {elapsed:.1f}s. '
                    f'Tail: {out.strip()[-300:]}'
                ))
            elif 'authentication_error' in out or 'Invalid authentication' in out:
                findings.append((
                    'CRITICAL', slug,
                    f'claude -p succeeded but output mentions authentication_error. '
                    f'Refresh token: docker exec -it outreach_cron claude setup-token'
                ))
            elif 'pong' not in out.lower():
                findings.append((
                    'WARN', slug,
                    f'claude -p returned 0 but did not echo pong in {elapsed:.1f}s. '
                    f'Tail: {out.strip()[-200:]}'
                ))
            else:
                self.stdout.write(f'[INFO ] cli_auth: pong in {elapsed:.1f}s')
        except FileNotFoundError:
            findings.append(('CRITICAL', slug, 'claude binary not found on PATH'))
        except subprocess.TimeoutExpired:
            findings.append(('CRITICAL', slug, 'claude -p timed out after 45s'))
        except Exception as exc:
            findings.append(('WARN', slug, f'claude probe raised {type(exc).__name__}: {exc}'))

    def _check_reply_log(self, findings):
        """Scan /tmp/outreach_reply_monitor.log for recent failure streaks.

        Counts lines matching 'Claude exited with code' in the trailing
        200 lines (~last hour of cron output). Fires WARN at 3+, CRITICAL
        at 10+. This is cheap line counting, not log parsing, so it works
        on both hosts without any shared log infra.
        """
        slug = 'reply_log'
        log_path = Path('/tmp/outreach_reply_monitor.log')
        if not log_path.exists():
            return  # Silent: log may not exist on dev machines

        try:
            # Read just the tail to avoid loading a multi-MB file
            with log_path.open('rb') as fh:
                fh.seek(0, 2)
                size = fh.tell()
                fh.seek(max(0, size - 200_000))  # last ~200KB
                tail = fh.read().decode('utf-8', errors='replace')
        except Exception as exc:
            findings.append(('WARN', slug, f'could not tail {log_path}: {exc}'))
            return

        recent_lines = tail.splitlines()[-200:]
        failures = sum(1 for ln in recent_lines if 'Claude exited with code' in ln)
        if failures >= 10:
            findings.append((
                'CRITICAL', slug,
                f'{failures} "Claude exited with code" lines in last 200 log entries. '
                f'Reply pipeline is almost certainly broken. Check CLI auth.'
            ))
        elif failures >= 3:
            findings.append((
                'WARN', slug,
                f'{failures} "Claude exited with code" lines in last 200 log entries. '
                f'Investigate before backlog grows.'
            ))
