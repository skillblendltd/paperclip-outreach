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
import re
import subprocess
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone

from campaigns.models import InboundEmail, Product, PromptTemplate, EmailLog

logger = logging.getLogger(__name__)

# Skill file fallbacks (used when no PromptTemplate in DB)
SKILL_FALLBACKS = {
    'taggiq': '/taggiq-email-expert',
    'fullypromoted': '/fp-email-expert',
}

# Claude CLI binary - resolved via PATH (installed in container by Dockerfile,
# or user-local install on developer machines)
CLAUDE_CLI = 'claude'

# Deterministic violation detectors run after every AI reply batch.
# These catch rule violations the prompt is supposed to prevent but Claude
# might emit anyway. Cheap regex - no LLM call, runs on every tick.

# Match a price quote in any currency or phrasing that anchors the prospect.
# Designed to fire on real quotes ("EUR 18", "around 25 each", "from €15-20")
# and skip false positives (signature address "A20", phone "01-485-1205",
# qty markers "10+", "20+ items").
_PRICE_PATTERNS = [
    # Currency followed by a number (EUR 18, € 25, euros 30, $40, £15)
    re.compile(r'\b(?:eur|euros?|€|gbp|£|usd|\$)\s*\d{1,4}(?:[.,]\d{1,2})?\b', re.IGNORECASE),
    # A number followed by currency (18 EUR, 25€, 30 GBP)
    re.compile(r'\b\d{1,4}(?:[.,]\d{1,2})?\s*(?:eur|euros?|€|gbp|£)\b', re.IGNORECASE),
    # "X each / per item / per piece / per unit" - direct unit pricing
    re.compile(r'\b\d{1,4}(?:[.,]\d{1,2})?\s*(?:each|per\s*(?:item|piece|unit)|/\s*(?:item|piece|unit))\b', re.IGNORECASE),
    # Numeric range explicitly tied to "each" or currency (15-20 EUR, 18 - 25 each)
    re.compile(r'\b\d{1,4}\s*[-–to]+\s*\d{1,4}\s*(?:eur|euros?|€|gbp|£|each)\b', re.IGNORECASE),
]

# Bounce / autoresponder addresses. Replying to these causes loops and bad reputation.
_BOUNCE_LOCAL_PARTS = re.compile(
    r'^(mailer-daemon|postmaster|no-?reply|bounce|bounces|delivery|notifications?|do-?not-?reply|abuse)@',
    re.IGNORECASE,
)


def _strip_html(s):
    return re.sub(r'<[^>]+>', ' ', s or '')


def _detect_price_violation(body_html):
    """Return the first matching price pattern's match text, or None."""
    text = _strip_html(body_html)
    # Strip the signature block (everything from "Cheers,\nLisa" or signature contact line) -
    # we explicitly allow the address "A20" and phone "01-485-1205" in the signature.
    sig_split = re.split(r'(?i)\b(?:cheers|thanks|regards|kind regards),?\s*\n+\s*lisa\b', text, maxsplit=1)
    body_only = sig_split[0] if sig_split else text
    for pat in _PRICE_PATTERNS:
        m = pat.search(body_only)
        if m:
            return m.group(0)
    return None


def _detect_bounce_reply(to_email):
    if not to_email:
        return False
    return bool(_BOUNCE_LOCAL_PARTS.match(to_email))


# Length thresholds (words, excluding signature). Lisa target is <100.
# Warn at 130, fail at 180. Anything over the warn threshold gets logged.
_LENGTH_WARN_WORDS = 130
_LENGTH_FAIL_WORDS = 180


def _detect_length_violation(body_html):
    """Count words in the body excluding the signature block.

    Returns (word_count, severity) where severity is one of:
      None  - within budget
      'warn' - over warn threshold but under fail threshold
      'fail' - over fail threshold
    """
    text = _strip_html(body_html)
    # Strip the signature block (same heuristic as price detector)
    sig_split = re.split(
        r'(?i)\b(?:cheers|thanks|regards|kind regards|best),?\s*\n+\s*lisa\b',
        text, maxsplit=1,
    )
    body_only = sig_split[0] if sig_split else text
    # Collapse whitespace and count
    words = [w for w in re.split(r'\s+', body_only.strip()) if w]
    n = len(words)
    if n >= _LENGTH_FAIL_WORDS:
        return n, 'fail'
    if n >= _LENGTH_WARN_WORDS:
        return n, 'warn'
    return n, None


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

        # Step 5: Audit AI replies sent in the last 30 minutes for rule violations.
        # Cheap deterministic checks - no LLM call. Loud warnings if the prompt
        # is being violated (price quoted, replied to a bounce, etc).
        self._audit_recent_ai_replies(product_filter, exclude_product)

    def _audit_recent_ai_replies(self, product_filter, exclude_product):
        """Run deterministic violation checks on AI replies from the last 30 min.

        Catches prompt rule violations the AI might emit anyway:
          - Price quoted in the body (Lisa is forbidden to quote prices)
          - Reply sent to a bounce / mailer-daemon / postmaster address
        Logs WARNING for each violation, scoped to the same product filter
        the cron run used so each host only audits its own work.
        """
        since = timezone.now() - timedelta(minutes=30)
        qs = EmailLog.objects.filter(
            triggered_by='ai_reply',
            created_at__gte=since,
        ).select_related('campaign__product_ref', 'prospect')
        if product_filter:
            qs = qs.filter(campaign__product_ref__slug=product_filter)
        if exclude_product:
            qs = qs.exclude(campaign__product_ref__slug=exclude_product)

        total = qs.count()
        if total == 0:
            return

        self.stdout.write(f'\n--- Auditing {total} AI reply(s) from last 30 min ---')
        violations = 0
        for log in qs:
            who = f'{log.to_email} ({log.prospect.business_name if log.prospect else "-"})'
            price_match = _detect_price_violation(log.body_html)
            if price_match:
                violations += 1
                self.stderr.write(self.style.ERROR(
                    f'  PRICE-QUOTE VIOLATION → {who}: matched "{price_match}" in subject "{log.subject[:60]}"'
                ))
                logger.error(
                    'lisa_violation price_quote inbound_to=%s match=%s subject=%s',
                    log.to_email, price_match, log.subject,
                )
            if _detect_bounce_reply(log.to_email):
                violations += 1
                self.stderr.write(self.style.ERROR(
                    f'  BOUNCE-REPLY VIOLATION → {who}: replied to bounce/autoresponder address'
                ))
                logger.error(
                    'lisa_violation bounce_reply inbound_to=%s subject=%s',
                    log.to_email, log.subject,
                )
            word_count, length_severity = _detect_length_violation(log.body_html)
            if length_severity == 'fail':
                violations += 1
                self.stderr.write(self.style.ERROR(
                    f'  LENGTH-FAIL VIOLATION → {who}: {word_count} words (limit {_LENGTH_FAIL_WORDS}) in subject "{log.subject[:60]}"'
                ))
                logger.error(
                    'lisa_violation length_fail words=%d inbound_to=%s subject=%s',
                    word_count, log.to_email, log.subject,
                )
            elif length_severity == 'warn':
                self.stderr.write(self.style.WARNING(
                    f'  LENGTH-WARN → {who}: {word_count} words (warn at {_LENGTH_WARN_WORDS}, target <100)'
                ))
                logger.warning(
                    'lisa_audit length_warn words=%d inbound_to=%s subject=%s',
                    word_count, log.to_email, log.subject,
                )
        if violations == 0:
            self.stdout.write(self.style.SUCCESS(f'  audit clean: {total} reply(s), 0 violations'))
        else:
            self.stdout.write(self.style.WARNING(f'  audit found {violations} violation(s) across {total} reply(s)'))

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
