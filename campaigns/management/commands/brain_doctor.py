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

import sys

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

    def handle(self, *args, **opts):
        findings = []  # (severity, brain_slug, message)

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
