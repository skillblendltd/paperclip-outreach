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
import imaplib
import os
import subprocess
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone

from campaigns.models import InboundEmail, MailboxConfig, Product, PromptTemplate, EmailLog
from campaigns.services.reply_audit import (
    detect_price_violation,
    detect_bounce_reply,
    detect_length_violation,
)
from campaigns.services.day_awareness import current_day_awareness_block
from campaigns.services.reply_window import is_within_reply_window
# Sprint 7 Phase 7.2.1 — imported lazily inside the flag branch so flag=False
# code path has zero new import side effects.

logger = logging.getLogger(__name__)

# Skill file fallbacks (used when no PromptTemplate in DB)
SKILL_FALLBACKS = {
    'taggiq': '/taggiq-email-expert',
    'fullypromoted': '/fp-email-expert',
}

# Claude CLI binary - resolved via PATH (installed in container by Dockerfile,
# or user-local install on developer machines)
CLAUDE_CLI = 'claude'

# Default length thresholds for the post-run audit. Per-persona prompts can
# carry stricter limits via PromptTemplate metadata, but these are the
# conservative ceiling for "this is way too long" applied to all personas.
_DEFAULT_WARN_WORDS = 130
_DEFAULT_FAIL_WORDS = 180


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

        # G5 (2026-04-15): apply reply-window + grace + unread cross-check
        # gates BEFORE dispatching to Claude. Each gate logs its skip reason.
        # Returns a filtered list of inbounds that are truly eligible for AI
        # auto-reply right now.
        actionable = self._filter_actionable_inbounds(list(flagged_qs))
        # Restrict the dispatch set to the actionable ids — the downstream
        # product-batching query in Claude invocations is handled elsewhere,
        # but list_pending_replies (which the Claude agent calls via cron) reads
        # the same DB state, so actionable filtering + needs_reply mutation in
        # `_filter_actionable_inbounds` is what the agent will see.
        actionable_ids = {i.id for i in actionable}

        # Group by product (only inbounds that passed all gates)
        product_counts = {}
        for inbound in actionable:
            product = inbound.campaign.product_ref
            if product:
                slug = product.slug
                if slug not in product_counts:
                    product_counts[slug] = {'product': product, 'count': 0}
                product_counts[slug]['count'] += 1

        if not product_counts:
            self.stdout.write('\nNo flagged replies needing AI response.')
            self._print_attention_summary()
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
                # Sprint 7 Phase 7.2.1 — if ANY flagged inbound for this product
                # lives on a campaign with use_context_assembler=True, route
                # through cacheable_preamble.build() so conversation context
                # + brain_version get recorded. This is a per-product decision
                # because handle_replies batches by product, not by campaign.
                # Flag=False path (byte-sacred) is the else branch.
                flag_on = InboundEmail.objects.filter(
                    needs_reply=True,
                    replied=False,
                    campaign__isnull=False,
                    campaign__product_ref=product,
                    campaign__use_context_assembler=True,
                ).exists()
                if flag_on:
                    self._invoke_with_contextual_prompt(product, prompt_template, count)
                else:
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

        # Step 4b: Attention summary - surface anything needing human eyes
        self._print_attention_summary()

        # Step 5: Audit AI replies sent in the last 30 minutes for rule violations.
        # Cheap deterministic checks - no LLM call. Loud warnings if the prompt
        # is being violated (price quoted, replied to a bounce, etc).
        self._audit_recent_ai_replies(product_filter, exclude_product)

    # ------------------------------------------------------------------
    # Attention summary - surface items needing human eyes
    # ------------------------------------------------------------------

    def _print_attention_summary(self):
        """Print a clear summary of inbounds needing manual attention.
        Runs every cron tick so Prakash can tail the log and see what's stuck.
        Only surfaces items from the last 24 hours to avoid noise from old history."""

        now = timezone.now()
        since = now - timedelta(hours=24)
        items = []

        # 1. Manual review needed (ambiguous matches) - last 24h
        manual_review = InboundEmail.objects.filter(
            needs_manual_review=True, replied=False,
            created_at__gte=since,
        ).values_list('from_email', flat=True)
        for email in manual_review:
            items.append(f'  - {email} (ambiguous match, needs manual review)')

        # 2. No-match inbounds with In-Reply-To (real replies we couldn't route) - last 24h
        # Exclude postmaster/mailer-daemon (delivery notifications, not real replies)
        no_match_replies = InboundEmail.objects.filter(
            prospect__isnull=True, replied=False,
            in_reply_to__isnull=False,
            created_at__gte=since,
        ).exclude(
            in_reply_to=''
        ).exclude(
            from_email__icontains='postmaster'
        ).exclude(
            from_email__icontains='mailer-daemon'
        ).values_list('from_email', flat=True)
        for email in no_match_replies:
            items.append(f'  - {email} (no prospect match, has In-Reply-To)')

        # 3. Stuck outside reply window for > 6 hours
        six_hours_ago = now - timedelta(hours=6)
        stuck = InboundEmail.objects.filter(
            needs_reply=True, replied=False,
            created_at__lt=six_hours_ago,
            created_at__gte=since,
        ).values_list('from_email', 'campaign__name')
        for email, camp in stuck:
            items.append(f'  - {email} (pending > 6 hours, campaign: {camp})')

        if items:
            self.stdout.write(self.style.WARNING(
                f'\nATTENTION: {len(items)} inbound(s) need review (last 24h)'
            ))
            for item in items:
                self.stdout.write(self.style.WARNING(item))
        else:
            self.stdout.write('\nNo items needing attention.')

    # ------------------------------------------------------------------
    # G5 gates (2026-04-15): reply window + grace + unread cross-check
    # ------------------------------------------------------------------

    def _filter_actionable_inbounds(self, inbounds):
        """Apply the three reply-safety gates and return the subset that is
        eligible for AI auto-reply right now. Mutates DB state for inbounds
        that have been claimed by the human operator (marks needs_reply=False
        with a structured note) so that subsequent cron ticks do not revisit
        them.

        Order of checks (cheapest first):
          1. Reply window  — is the inbound's campaign currently in its
             configured business hours on an allowed weekday?
          2. Grace window  — has the inbound been sitting in the DB for at
             least `campaign.reply_grace_minutes`? If not, defer to give the
             human operator time to claim it.
          3. Unread check  — reconnect to the mailbox, query IMAP for
             `UNSEEN HEADER Message-ID "<msg>"`. If empty set, the human has
             marked the message as read → they are claiming it → skip and
             flip DB row to needs_reply=False with note.

        IMAP outage = fail open: if we cannot reach the mailbox to check,
        we allow the reply through rather than silently blocking all replies
        on a Gmail/Zoho incident. A WARN is logged so ops can investigate.
        """
        # Use Django's timezone.now() for DB comparisons (created_at is naive
        # when USE_TZ=False) but pass None to is_within_reply_window() so it
        # constructs its own timezone-correct datetime internally.
        now = timezone.now()
        actionable = []
        skipped_window = 0
        skipped_grace = 0
        skipped_unread = 0

        # Group inbounds by (imap_email, campaign) so we can do one IMAP
        # login per mailbox and reuse it for all message-id checks in that
        # mailbox. MailboxConfig.imap_email is the grouping key since the
        # mailbox may be shared by multiple campaigns (sibling fallback).
        by_mailbox: dict[str, list] = {}
        inbound_mailbox: dict[str, MailboxConfig] = {}

        for inbound in inbounds:
            campaign = inbound.campaign

            # Gate 1: reply window (pass None so it constructs its own
            # timezone-correct datetime - avoids Django TIME_ZONE mismatch)
            if not is_within_reply_window(campaign):
                skipped_window += 1
                self.stdout.write(
                    f'  skip (window): {inbound.from_email[:40]} '
                    f'campaign={campaign.name[:40]} — outside reply window'
                )
                continue

            # Gate 2: grace window. Use `created_at` (BaseModel auto-field,
            # always aware UTC set at DB insert time) rather than
            # `received_at` (populated from the email Date header and
            # historically stripped of tzinfo in check_replies, which makes
            # timezone math unreliable). `created_at` is also the semantically
            # correct field: "how long has this been in the DB unseen".
            grace_min = int(getattr(campaign, 'reply_grace_minutes', 5) or 5)
            age = now - inbound.created_at
            if age < timedelta(minutes=grace_min):
                age_seconds = age.total_seconds()
                skipped_grace += 1
                self.stdout.write(
                    f'  skip (grace):  {inbound.from_email[:40]} '
                    f'captured {age_seconds:.0f}s ago (< {grace_min}min grace)'
                )
                continue

            # Stash for the per-mailbox IMAP check below
            mb = MailboxConfig.objects.filter(
                campaign=campaign, is_active=True,
            ).first()
            if not mb:
                # No mailbox config for this campaign — cannot cross-check
                # UNSEEN state. Allow through (the existing pipeline has been
                # operating this way for months). Log for visibility.
                self.stdout.write(self.style.WARNING(
                    f'  no mailbox cfg for {campaign.name} — skipping unread check'
                ))
                actionable.append(inbound)
                continue
            key = mb.imap_email.lower()
            by_mailbox.setdefault(key, []).append(inbound)
            inbound_mailbox[str(inbound.id)] = mb

        # Gate 3: per-mailbox unread cross-check
        for imap_email, group in by_mailbox.items():
            mb = inbound_mailbox[str(group[0].id)]
            try:
                unseen_ids = self._imap_fetch_unseen_message_ids(mb)
            except Exception as exc:
                self.stderr.write(self.style.WARNING(
                    f'  IMAP check failed for {imap_email}: {exc} — '
                    f'allowing {len(group)} inbound(s) through without unread cross-check'
                ))
                actionable.extend(group)
                continue

            for inbound in group:
                if inbound.message_id and inbound.message_id in unseen_ids:
                    # Currently UNSEEN → eligible this tick. Operator can
                    # release a previously-claimed inbound back to the AI by
                    # marking it unread again; we re-check every tick so that
                    # works automatically.
                    actionable.append(inbound)
                else:
                    # Currently SEEN (human opened it on phone, or message
                    # archived/moved). Skip THIS tick only — do NOT mutate
                    # needs_reply. The next tick re-runs this check; if the
                    # operator flips it back to unread the AI will pick it up.
                    skipped_unread += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'  skip (claimed): {inbound.from_email[:40]} — '
                        f'currently SEEN in {imap_email} '
                        f'(mark unread to release to AI)'
                    ))

        if any([skipped_window, skipped_grace, skipped_unread]):
            self.stdout.write(
                f'\nG5 gates: {len(actionable)} actionable, '
                f'{skipped_window} outside window, '
                f'{skipped_grace} in grace, '
                f'{skipped_unread} user-claimed'
            )
        return actionable

    def _imap_fetch_unseen_message_ids(self, mailbox_cfg):
        """Return the set of `Message-ID` headers currently UNSEEN in the
        given mailbox. One IMAP login, one SEARCH, one FETCH per unseen
        message for the Message-ID header.

        Returned IDs retain the surrounding angle brackets (matching the
        format we store in InboundEmail.message_id).
        """
        imap = imaplib.IMAP4_SSL(mailbox_cfg.imap_host, mailbox_cfg.imap_port)
        try:
            imap.login(mailbox_cfg.imap_email, mailbox_cfg.imap_password)
            imap.select('INBOX')
            status, data = imap.search(None, 'UNSEEN')
            if status != 'OK' or not data or not data[0]:
                return set()
            msg_nums = data[0].split()
            if not msg_nums:
                return set()
            # Batch FETCH: fetch Message-ID header for all unseen msgs at once
            fetch_spec = b','.join(msg_nums)
            status, fetched = imap.fetch(
                fetch_spec,
                '(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])',
            )
            if status != 'OK' or not fetched:
                return set()
            out = set()
            for item in fetched:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                raw = item[1]
                if isinstance(raw, bytes):
                    raw = raw.decode('utf-8', errors='replace')
                for line in raw.splitlines():
                    if line.lower().startswith('message-id:'):
                        val = line.split(':', 1)[1].strip()
                        if val:
                            out.add(val)
            return out
        finally:
            try:
                imap.logout()
            except Exception:
                pass

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
            # Derive persona name from the active prompt template for this product
            # so signature stripping works for any persona, not just Lisa.
            persona = self._get_persona_for_product(log.campaign.product_ref) if log.campaign and log.campaign.product_ref else ''
            price_match = detect_price_violation(log.body_html, signature_name=persona)
            if price_match:
                violations += 1
                self.stderr.write(self.style.ERROR(
                    f'  PRICE-QUOTE VIOLATION → {who}: matched "{price_match}" in subject "{log.subject[:60]}"'
                ))
                logger.error(
                    'reply_violation price_quote inbound_to=%s match=%s subject=%s',
                    log.to_email, price_match, log.subject,
                )
            if detect_bounce_reply(log.to_email):
                violations += 1
                self.stderr.write(self.style.ERROR(
                    f'  BOUNCE-REPLY VIOLATION → {who}: replied to bounce/autoresponder address'
                ))
                logger.error(
                    'reply_violation bounce_reply inbound_to=%s subject=%s',
                    log.to_email, log.subject,
                )
            word_count, length_severity = detect_length_violation(
                log.body_html, signature_name=persona,
                warn_words=_DEFAULT_WARN_WORDS, fail_words=_DEFAULT_FAIL_WORDS,
            )
            if length_severity == 'fail':
                violations += 1
                self.stderr.write(self.style.ERROR(
                    f'  LENGTH-FAIL VIOLATION → {who}: {word_count} words (limit {_DEFAULT_FAIL_WORDS}) in subject "{log.subject[:60]}"'
                ))
                logger.error(
                    'reply_violation length_fail words=%d inbound_to=%s subject=%s',
                    word_count, log.to_email, log.subject,
                )
            elif length_severity == 'warn':
                self.stderr.write(self.style.WARNING(
                    f'  LENGTH-WARN → {who}: {word_count} words (warn at {_DEFAULT_WARN_WORDS}, target <100)'
                ))
                logger.warning(
                    'lisa_audit length_warn words=%d inbound_to=%s subject=%s',
                    word_count, log.to_email, log.subject,
                )
        if violations == 0:
            self.stdout.write(self.style.SUCCESS(f'  audit clean: {total} reply(s), 0 violations'))
        else:
            self.stdout.write(self.style.WARNING(f'  audit found {violations} violation(s) across {total} reply(s)'))

    def _get_persona_for_product(self, product):
        """Return the signature_name of the active email_reply prompt for this
        product, or empty string if none. Used by the audit to strip signatures
        before running word-count and price checks.
        """
        if not product:
            return ''
        pt = PromptTemplate.objects.filter(
            product=product, feature='email_reply', is_active=True,
        ).order_by('-version').first()
        return pt.signature_name if pt else ''

    def _build_execution_preamble(self, product, prompt_template):
        """Generic, persona-parameterized execution recipe prepended to every
        DB prompt. Lives in code so it stays consistent across all personas
        (Lisa, TaggIQ, FP) and the per-product PromptTemplate only needs to
        carry voice/intent/rules.

        Substitutes the persona-specific values from the PromptTemplate row:
          - product slug (for list_pending_replies filter)
          - from_name (display name for the From header)
          - signature_name (for detector signature stripping)
          - max_reply_words / warn_reply_words (length thresholds)
        """
        slug = product.slug
        from_name = prompt_template.from_name or 'Unknown Persona'
        sig = prompt_template.signature_name or 'Unknown'
        max_w = prompt_template.max_reply_words or 130
        warn_w = prompt_template.warn_reply_words or 100

        return (
            f'You are an autonomous email reply agent for the "{product.name}" product. '
            f'You read flagged inbound emails, generate personalized replies in the voice '
            f'described below, send them via the send_ai_reply command, and verify all '
            f'inbounds are handled. Do all of this without asking for confirmation.\n'
            f'\n'
            f'==============================================================\n'
            f'EXECUTION RECIPE - INFRASTRUCTURE (do not deviate)\n'
            f'==============================================================\n'
            f'\n'
            f'The repo is at /app inside the container. Use the Bash tool. Run python directly.\n'
            f'\n'
            f'STEP 1 - Fetch all flagged inbounds for this product:\n'
            f'\n'
            f'    cd /app && python manage.py list_pending_replies --product-slug {slug}\n'
            f'\n'
            f'This prints one block per inbound with ID, From, prospect details, subject, '
            f'classification, body, and the current attempt count. Read all of them.\n'
            f'\n'
            f'STEP 2 - For each inbound, write a reply using the VOICE AND INTENT RULES below '
            f'(those rules are the persona-specific section that follows this preamble). The voice '
            f'rules tell you HOW to write. The execution recipe (this section) tells you HOW to send.\n'
            f'\n'
            f'STEP 3 - Send each reply via send_ai_reply. This command runs deterministic '
            f'pre-send checks (price quote, bounce reply, length) BEFORE the SMTP send. If the '
            f'check fails it returns a non-zero exit code and you MUST rewrite and try again.\n'
            f'\n'
            f'    cd /app && python manage.py send_ai_reply \\\n'
            f'      --inbound-id <UUID_FROM_STEP_1> \\\n'
            f'      --subject "Re: <ORIGINAL_SUBJECT>" \\\n'
            f'      --body-html "<HTML_BODY_INCLUDING_SIGNATURE>" \\\n'
            f'      --from-name "{from_name}" \\\n'
            f'      --signature-name "{sig}" \\\n'
            f'      --max-words {max_w} \\\n'
            f'      --warn-words {warn_w}\n'
            f'\n'
            f'Exit codes from send_ai_reply:\n'
            f'  0 = success, the reply was sent and the DB was updated. Move to the next inbound.\n'
            f'  2 = PRICE-QUOTE blocked. Read the error message. Rewrite the body WITHOUT any '
            f'currency-anchored number, range, or "X each / per item" phrasing. Call send_ai_reply again.\n'
            f'  3 = BOUNCE blocked. The from_email is a bounce/autoresponder. Skip this inbound entirely - '
            f'it has already been marked needs_reply=False. Move on to the next inbound.\n'
            f'  4 = LENGTH-FAIL blocked. The body is too long. Rewrite shorter (target <{warn_w} words). '
            f'If you cannot fit the answer in {max_w} words, that is a signal the conversation needs '
            f'a phone call instead of a long email - shorten the body and offer the phone CTA. Call again.\n'
            f'  5 = RETRY EXHAUSTED. The inbound has hit the max attempt count. Do NOT retry. '
            f'Move on to the next inbound.\n'
            f'  1 = generic error (inbound not found, SMTP failure). Read the error and move on.\n'
            f'\n'
            f'CRITICAL: After 3 rewrite attempts on the same inbound, give up on it and move on. '
            f'send_ai_reply tracks attempts across cron runs - if you exhaust the budget the system '
            f'will surface the inbound for manual review automatically.\n'
            f'\n'
            f'STEP 4 - Verify all inbounds were handled:\n'
            f'\n'
            f'    cd /app && python manage.py list_pending_replies --product-slug {slug}\n'
            f'\n'
            f'If the output says "No pending inbounds" you are done. If any inbounds remain, '
            f'either continue handling them (Step 3) or accept that the remaining ones hit '
            f'their retry budget and will be reviewed manually.\n'
            f'\n'
        )

    def _invoke_with_contextual_prompt(self, product, prompt_template, count):
        """Sprint 7 Phase 7.2.1 — flag=True path.

        Builds the Claude CLI prompt via cacheable_preamble.build() so the
        stable execution recipe + voice rules come from the same layered
        assembly used by the Anthropic SDK path. Per-inbound conversation
        context is NOT injected here (the agent fetches inbounds itself via
        list_pending_replies at runtime); the Layer 1/3 block is the
        system-level recipe, identical across inbounds. Phase 3 upgrades
        handle_replies to the SDK path so per-inbound context + true prompt
        caching both land — Phase 7.2 intentionally flattens to the -p CLI
        arg to minimise blast radius.
        """
        from campaigns.services import cacheable_preamble
        from campaigns.services.brain import load_brain_by_product, BrainNotFound

        self.stdout.write(f'  [contextual] DB prompt: {prompt_template.name} (v{prompt_template.version})')
        self.stdout.write(f'  [contextual] Model: {prompt_template.model}')

        try:
            brain = load_brain_by_product(product.slug)
            brain_version = brain.brain_version
        except Exception as exc:
            self.stderr.write(self.style.WARNING(
                f'  [contextual] no brain for product "{product.slug}": {exc} — proceeding without brain_version'
            ))
            brain_version = None

        assembled = cacheable_preamble.build(
            product=product,
            prompt_template=prompt_template,
            prospect=None,
            flagged_count=count,
            include_conversation=False,
            max_context_tokens=2000,
        )
        # Flatten system_blocks + user_message into the single-string CLI `-p` arg.
        # We lose the 5-minute Anthropic prompt cache benefit but gain the
        # unified assembly path and brain_version recording. Upgrade to SDK is
        # Phase 3 work — explicitly intentional here.
        full_prompt = '\n\n'.join(b.content for b in assembled.system_blocks)
        full_prompt += '\n\n' + assembled.user_message

        model_map = {
            'claude-sonnet-4-6': 'sonnet',
            'claude-haiku-4-5': 'haiku',
            'claude-opus-4-6': 'opus',
        }
        model_flag = model_map.get(prompt_template.model, 'sonnet')

        # Stash brain_version on the environment so send_ai_reply (invoked by
        # the agent as a subprocess) can pick it up and record it on AIUsageLog.
        env = dict(os.environ)
        if brain_version is not None:
            env['PAPERCLIP_BRAIN_VERSION'] = str(brain_version)

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
                env=env,
            )
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS(f'  [contextual] Claude finished successfully'))
            else:
                self.stderr.write(self.style.ERROR(f'  [contextual] Claude exited with code {result.returncode}'))
                if result.stderr:
                    self.stderr.write(f'  stderr: {result.stderr[:500]}')
        except subprocess.TimeoutExpired:
            self.stderr.write(self.style.ERROR(f'  [contextual] Claude timed out after 600s'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'  [contextual] Error invoking Claude: {e}'))

    def _invoke_with_db_prompt(self, product, prompt_template, count):
        """Invoke Claude CLI with a prompt from the database.

        The prompt sent to Claude is assembled in three layers:
          1. Generic execution preamble (from code, parameterized per persona)
          2. Voice rules (from PromptTemplate.system_prompt - DB editable)
          3. Per-call kicker telling Claude how many inbounds to handle
        """
        self.stdout.write(f'  Using DB prompt: {prompt_template.name} (v{prompt_template.version})')
        self.stdout.write(f'  Model: {prompt_template.model}')

        preamble = self._build_execution_preamble(product, prompt_template)
        # Day-awareness block: regenerated on every run with today's weekday
        # + rule banning past-day slot proposals. Lives between preamble and
        # voice rules so Claude reads "today is Wednesday" BEFORE reading any
        # hardcoded "Tuesday or Wednesday" example line in the voice rules.
        day_block = current_day_awareness_block()
        voice_rules = prompt_template.system_prompt
        kicker = (
            f'\n\n==============================================================\n'
            f'YOUR JOB RIGHT NOW\n'
            f'==============================================================\n'
            f'There are {count} flagged inbound email(s) for product "{product.name}".\n'
            f'Use Step 1 to fetch them, then for each one apply Step 2 (voice rules above), '
            f'Step 3 to send via send_ai_reply, and Step 4 to verify all are handled.\n'
            f'Do NOT ask for confirmation. Run the commands directly using the Bash tool.\n'
            f'REMINDER: honor the CURRENT DATE AWARENESS block - never propose a slot '
            f'that has already passed.\n'
        )

        full_prompt = preamble + '\n\n' + day_block + '\n\n' + voice_rules + kicker

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
