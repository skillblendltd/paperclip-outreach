"""Sprint 7 Phase 7.0.2 — eval_golden management command.

Runs the golden-set harness for a product (or all products) and prints
a summary. Exits non-zero if any product drops below its brain's
eval_threshold_pct, so it can be used as a pre-merge gate.

Examples:
    python manage.py eval_golden --product taggiq
    python manage.py eval_golden --all
    python manage.py eval_golden --product fullypromoted --verbose
    python manage.py eval_golden --all --baseline  # writes baseline.json

Phase 7.0 runs in rule-based mode only (no LLM). Phase 7.2 will add
--judge flag for Opus 4.6 scoring.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from django.core.management.base import BaseCommand

from campaigns.models import Product, ProductBrain
from campaigns.services.eval_harness import run_eval


class Command(BaseCommand):
    help = 'Run the golden-set eval harness for a product (or all).'

    def add_arguments(self, parser):
        parser.add_argument('--product', help='Product slug, e.g. taggiq')
        parser.add_argument('--all', action='store_true', help='Eval every product with an active brain')
        parser.add_argument('--verbose', action='store_true', help='Show per-pair results')
        parser.add_argument('--baseline', action='store_true',
                            help='Write tests/golden_sets/baseline.json with current scores')
        parser.add_argument('--strict', action='store_true',
                            help='Exit 1 if any product below its eval_threshold_pct')

    def handle(self, *args, **opts):
        only = opts.get('product')
        do_all = opts.get('all')
        verbose = opts.get('verbose')
        write_baseline = opts.get('baseline')
        strict = opts.get('strict')

        if not (only or do_all):
            self.stderr.write('Must pass --product X or --all')
            sys.exit(2)

        if only:
            slugs = [only]
        else:
            slugs = list(ProductBrain.objects.filter(is_active=True)
                         .values_list('product__slug', flat=True).order_by('product__slug'))

        if not slugs:
            self.stdout.write(self.style.WARNING('No active ProductBrains found.'))
            return

        all_reports = {}
        failures = []

        for slug in slugs:
            report = run_eval(slug, mode='rule_based')
            all_reports[slug] = {
                'brain_version': report.brain_version,
                'prompt_template': f'{report.prompt_template_name} v{report.prompt_template_version}',
                'total_pairs': report.total_pairs,
                'passed_pairs': report.passed_pairs,
                'score_pct': report.score_pct,
                'mode': report.mode,
            }

            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(f'=== {slug} ==='))
            self.stdout.write(f'  brain:  v{report.brain_version}')
            self.stdout.write(f'  voice:  {report.prompt_template_name} v{report.prompt_template_version}')
            self.stdout.write(f'  pairs:  {report.passed_pairs}/{report.total_pairs} passed')
            self.stdout.write(f'  score:  {report.score_pct}%')
            self.stdout.write(f'  mode:   {report.mode}')

            if verbose or report.score_pct < 100:
                for r in report.results:
                    marker = '✓' if r.passed else '✗'
                    self.stdout.write(f'    {marker} {r.pair_id} ({r.classification}) {r.score_pct}%')
                    for issue in r.issues:
                        self.stdout.write(f'        - {issue}')

            # Threshold check
            try:
                pb = ProductBrain.objects.get(product__slug=slug, is_active=True)
                threshold = pb.eval_threshold_pct or 90
            except ProductBrain.DoesNotExist:
                threshold = 90
            if report.score_pct < threshold:
                failures.append((slug, report.score_pct, threshold))

        if write_baseline:
            baseline_path = Path('tests/golden_sets/baseline.json')
            baseline_path.write_text(json.dumps(all_reports, indent=2) + '\n')
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(f'Baseline written: {baseline_path}'))

        self.stdout.write('')
        if failures:
            self.stdout.write(self.style.ERROR(f'FAIL: {len(failures)} product(s) below threshold'))
            for slug, got, thr in failures:
                self.stdout.write(f'  {slug}: {got}% < {thr}%')
            if strict:
                sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS('All products at or above threshold.'))
