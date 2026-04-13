"""
Autonomous reply handler - checks all mailboxes, then generates AI replies
using per-product PromptTemplate from DB (falls back to skill files).

Replaces the hardcoded run_reply_monitor.sh approach of always calling
/taggiq-email-expert for all replies.

Usage:
    python manage.py handle_replies                # All products
    python manage.py handle_replies --product taggiq  # One product only
    python manage.py handle_replies --dry-run      # Check but don't invoke Claude
"""
import os
import subprocess
import logging

from django.core.management.base import BaseCommand
from django.core.management import call_command

from campaigns.models import InboundEmail, Product, PromptTemplate

logger = logging.getLogger(__name__)

# Skill file fallbacks (used when no PromptTemplate in DB)
SKILL_FALLBACKS = {
    'taggiq': '/taggiq-email-expert',
    'fullypromoted': '/fp-email-expert',
}

# Claude CLI binary - resolved via PATH (installed in container by Dockerfile,
# or user-local install on developer machines)
CLAUDE_CLI = 'claude'


class Command(BaseCommand):
    help = 'Check all mailboxes for replies, then invoke AI reply per product using DB prompts'

    def add_arguments(self, parser):
        parser.add_argument('--product', help='Only handle replies for this product slug')
        parser.add_argument('--exclude-product', help='Exclude this product slug from reply handling and mailbox polling')
        parser.add_argument('--dry-run', action='store_true', help='Check mailboxes but do not invoke Claude')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        product_filter = options.get('product')
        exclude_product = options.get('exclude_product')

        # Step 1: Check mailboxes for new replies, scoped to product partition
        self.stdout.write('\n--- Checking mailboxes ---')
        check_kwargs = {'verbosity': 1, 'stdout': self.stdout, 'stderr': self.stderr}
        if product_filter:
            check_kwargs['product_slug'] = product_filter
        if exclude_product:
            check_kwargs['exclude_product_slug'] = exclude_product
        call_command('check_replies', **check_kwargs)

        # Step 2: Find flagged replies grouped by product
        flagged_qs = InboundEmail.objects.filter(
            needs_reply=True,
            replied=False,
            campaign__isnull=False,
        ).select_related('campaign__product_ref')

        if product_filter:
            flagged_qs = flagged_qs.filter(campaign__product_ref__slug=product_filter)
        if exclude_product:
            flagged_qs = flagged_qs.exclude(campaign__product_ref__slug=exclude_product)

        # Group by product
        product_counts = {}
        for inbound in flagged_qs:
            product = inbound.campaign.product_ref
            if product:
                slug = product.slug
                if slug not in product_counts:
                    product_counts[slug] = {'product': product, 'count': 0}
                product_counts[slug]['count'] += 1

        if not product_counts:
            self.stdout.write('\nNo flagged replies needing AI response.')
            return

        self.stdout.write(f'\n--- Flagged replies by product ---')
        for slug, info in product_counts.items():
            self.stdout.write(f'  {info["product"].name}: {info["count"]} reply(s)')

        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] Skipping Claude invocation.'))
            return

        # Step 3: Handle each product's replies
        for slug, info in product_counts.items():
            product = info['product']
            count = info['count']

            self.stdout.write(f'\n--- Handling {count} reply(s) for {product.name} ---')

            # Check for DB prompt first
            prompt_template = PromptTemplate.objects.filter(
                product=product,
                feature='email_reply',
                is_active=True,
            ).order_by('-version').first()

            if prompt_template:
                self._invoke_with_db_prompt(product, prompt_template, count)
            else:
                # Fall back to skill file
                skill = SKILL_FALLBACKS.get(slug)
                if skill:
                    self._invoke_with_skill(product, skill, count)
                else:
                    self.stderr.write(self.style.ERROR(
                        f'  No PromptTemplate in DB and no skill fallback for product "{slug}". '
                        f'{count} reply(s) need manual handling.'
                    ))

        # Step 4: Check remaining
        remaining = InboundEmail.objects.filter(
            needs_reply=True, replied=False, campaign__isnull=False,
        ).count()
        if remaining:
            self.stdout.write(self.style.WARNING(f'\n{remaining} reply(s) still pending after AI run.'))
        else:
            self.stdout.write(self.style.SUCCESS('\nAll replies handled.'))

    def _invoke_with_db_prompt(self, product, prompt_template, count):
        """Invoke Claude CLI with a prompt from the database."""
        self.stdout.write(f'  Using DB prompt: {prompt_template.name} (v{prompt_template.version})')
        self.stdout.write(f'  Model: {prompt_template.model}')

        # Build the prompt: system prompt + instruction to handle flagged replies
        full_prompt = (
            f'{prompt_template.system_prompt}\n\n'
            f'There are {count} flagged inbound email(s) for product "{product.name}" '
            f'that need replies. Check InboundEmail records where needs_reply=True and '
            f'replied=False and campaign__product_ref__slug="{product.slug}". '
            f'Read each email, generate a personalized reply in the voice described above, '
            f'send it via EmailService.send_reply(), and update the InboundEmail and Prospect records.'
        )

        # Map model names to Claude CLI model flags
        model_map = {
            'claude-sonnet-4-6': 'sonnet',
            'claude-haiku-4-5': 'haiku',
            'claude-opus-4-6': 'opus',
        }
        model_flag = model_map.get(prompt_template.model, 'sonnet')

        try:
            result = subprocess.run(
                [
                    CLAUDE_CLI,
                    '--model', model_flag,
                    '--allowedTools', 'Bash,Read,Write,Edit,Glob,Grep',
                    '--max-turns', '30',
                    '--output-format', 'text',
                    '-p', full_prompt,
                ],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=os.getenv('PAPERCLIP_REPO_DIR', '/app'),
            )
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS(f'  Claude finished successfully'))
            else:
                self.stderr.write(self.style.ERROR(f'  Claude exited with code {result.returncode}'))
                if result.stderr:
                    self.stderr.write(f'  stderr: {result.stderr[:500]}')
        except subprocess.TimeoutExpired:
            self.stderr.write(self.style.ERROR(f'  Claude timed out after 600s'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'  Error invoking Claude: {e}'))

    def _invoke_with_skill(self, product, skill_name, count):
        """Invoke Claude CLI with a hardcoded skill file (fallback)."""
        self.stdout.write(f'  Using skill fallback: {skill_name}')

        try:
            result = subprocess.run(
                [
                    CLAUDE_CLI,
                    '--model', 'sonnet',
                    '--allowedTools', 'Bash,Read,Write,Edit,Glob,Grep',
                    '--max-turns', '30',
                    '--output-format', 'text',
                    '-p', skill_name,
                ],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=os.getenv('PAPERCLIP_REPO_DIR', '/app'),
            )
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS(f'  Claude finished successfully'))
            else:
                self.stderr.write(self.style.ERROR(f'  Claude exited with code {result.returncode}'))
        except subprocess.TimeoutExpired:
            self.stderr.write(self.style.ERROR(f'  Claude timed out after 600s'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'  Error invoking Claude: {e}'))
