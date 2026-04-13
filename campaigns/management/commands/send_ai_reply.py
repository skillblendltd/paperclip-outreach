"""Send a single AI-generated reply to a flagged inbound.

This is the org-agnostic execution endpoint that every persona prompt (Lisa,
TaggIQ, FP) calls. The prompt provides the SUBJECT and BODY_HTML it wants to
send; this command does everything else:

  1. Look up the inbound + prospect + campaign + product
  2. Resolve SMTP via MailboxConfig (with sibling-campaign fallback)
  3. Run all deterministic detectors (price, bounce, length) PRE-SEND
       - if any fail-severity finding → refuse to send, exit 2/3/4
  4. Enforce per-inbound retry budget (max 5 attempts across cron runs)
  5. SMTP send via EmailService.send_reply with proper threading headers
  6. Create EmailLog audit row
  7. Increment InboundEmail.ai_attempt_count, mark replied=True on success
  8. Log to AIUsageLog (so per-persona cost is tracked)

Exit codes (so the calling Claude session can react smartly):
   0 = success, reply sent and logged
   1 = generic error (inbound not found, SMTP exception, etc)
   2 = PRICE-QUOTE violation - rewrite without currency-anchored numbers
   3 = BOUNCE-REPLY violation - do not reply to bounce/autoresponder addresses
   4 = LENGTH-FAIL violation - rewrite shorter
   5 = retry budget exhausted - move on, do not retry this inbound

Usage:
    python manage.py send_ai_reply \\
      --inbound-id <UUID> \\
      --subject "Re: ..." \\
      --body-html "<p>Hi ...</p>" \\
      --from-name "Lisa - Fully Promoted Dublin" \\
      --signature-name "Lisa" \\
      --max-words 130

The persona-specific args (--from-name, --signature-name, --max-words) are
required so this command never silently uses a Lisa-shaped default for
TaggIQ or FP. Each prompt declares its own persona.
"""
import sys
import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from campaigns.models import (
    InboundEmail, EmailLog, MailboxConfig, AIUsageLog,
)
from campaigns.email_service import EmailService
from campaigns.services.reply_audit import (
    detect_price_violation,
    detect_bounce_reply,
    detect_length_violation,
)
# Sprint 7 Phase 7.2.2 — budget gate + brain_version attribution
from campaigns.services import ai_budget


# Exit codes - keep stable, prompts depend on these
EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_PRICE = 2
EXIT_BOUNCE = 3
EXIT_LENGTH = 4
EXIT_RETRY_EXHAUSTED = 5

# Hard ceiling on retries per inbound across all cron runs. After this we
# stop trying to auto-reply and surface the inbound for manual review.
MAX_AI_ATTEMPTS = 5


class Command(BaseCommand):
    help = 'Send a single AI-generated reply to a flagged inbound (with pre-send blocking)'

    def add_arguments(self, parser):
        parser.add_argument('--inbound-id', required=True, help='UUID of the InboundEmail to reply to')
        parser.add_argument('--subject', required=True, help='Subject line for the reply (include Re: prefix)')
        parser.add_argument('--body-html', required=True, help='HTML body of the reply (signature included)')
        parser.add_argument('--from-name', required=True, help='Display name for the From header')
        parser.add_argument('--signature-name', required=True,
                            help='First-name anchor used by detectors to strip the signature block')
        parser.add_argument('--max-words', type=int, default=130,
                            help='Hard ceiling on body word count (default 130)')
        parser.add_argument('--warn-words', type=int, default=100,
                            help='Soft warn threshold for body word count (default 100)')

    def handle(self, *args, **options):
        inbound_id = options['inbound_id']
        subject = options['subject']
        body_html = options['body_html']
        from_name = options['from_name']
        signature_name = options['signature_name']
        max_words = options['max_words']
        warn_words = options['warn_words']

        # 1. Fetch inbound + relations
        try:
            inbound = InboundEmail.objects.select_related(
                'prospect', 'campaign__product_ref__organization',
            ).get(id=inbound_id)
        except InboundEmail.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'No InboundEmail with id={inbound_id}'))
            sys.exit(EXIT_GENERIC)

        # 2. Retry budget check (cross-cron)
        if inbound.ai_attempt_count >= MAX_AI_ATTEMPTS:
            self.stderr.write(self.style.ERROR(
                f'EXIT 5: retry budget exhausted for inbound {inbound.id} '
                f'(attempts={inbound.ai_attempt_count}, max={MAX_AI_ATTEMPTS}). '
                f'This inbound will not be auto-replied. Mark for manual review.'
            ))
            # Flag the inbound so it stops showing up in list_pending_replies
            inbound.notes = (inbound.notes + '\n' if inbound.notes else '') + \
                f'AI auto-reply abandoned after {MAX_AI_ATTEMPTS} attempts at {timezone.now().isoformat()}'
            inbound.needs_reply = False  # stop the audit loop
            inbound.save(update_fields=['notes', 'needs_reply', 'updated_at'])
            sys.exit(EXIT_RETRY_EXHAUSTED)

        prospect = inbound.prospect
        campaign = inbound.campaign
        product = campaign.product_ref if campaign else None

        if not campaign or not product:
            self.stderr.write(self.style.ERROR(
                f'Inbound {inbound.id} has no campaign or product_ref - cannot route reply'
            ))
            sys.exit(EXIT_GENERIC)

        # 3. Pre-send detectors (price, bounce, length) - HARD BLOCK on fail
        price_match = detect_price_violation(body_html, signature_name=signature_name)
        if price_match:
            self._increment_attempt(inbound)
            self.stderr.write(self.style.ERROR(
                f'EXIT 2 PRE-SEND BLOCK: price quote "{price_match}" detected in body. '
                f'Lisa/persona is forbidden from quoting prices. '
                f'Rewrite the body WITHOUT any currency-anchored number, range, or '
                f'"X each / per item" phrasing, then call send_ai_reply again.'
            ))
            sys.exit(EXIT_PRICE)

        if detect_bounce_reply(inbound.from_email):
            self._increment_attempt(inbound)
            self.stderr.write(self.style.ERROR(
                f'EXIT 3 PRE-SEND BLOCK: from_email {inbound.from_email} is a bounce/autoresponder. '
                f'Replying causes loops. Skip this inbound entirely - do not retry.'
            ))
            # Mark needs_reply=False so it stops getting picked up
            inbound.needs_reply = False
            inbound.notes = (inbound.notes + '\n' if inbound.notes else '') + \
                f'AI skipped bounce/autoresponder address at {timezone.now().isoformat()}'
            inbound.save(update_fields=['needs_reply', 'notes', 'updated_at'])
            sys.exit(EXIT_BOUNCE)

        word_count, length_severity = detect_length_violation(
            body_html, signature_name=signature_name,
            warn_words=warn_words, fail_words=max_words,
        )
        if length_severity == 'fail':
            self._increment_attempt(inbound)
            self.stderr.write(self.style.ERROR(
                f'EXIT 4 PRE-SEND BLOCK: body is {word_count} words (limit {max_words}). '
                f'Rewrite shorter - target is under {warn_words} words. '
                f'If the answer needs more space, that is a signal the conversation '
                f'needs a phone call instead of a long email.'
            ))
            sys.exit(EXIT_LENGTH)
        if length_severity == 'warn':
            self.stdout.write(self.style.WARNING(
                f'  LENGTH-WARN: body is {word_count} words (target <{warn_words})'
            ))

        # Sprint 7 Phase 7.2.2 — per-org AI budget gate. Only consulted when
        # the campaign is on the new contextual path; flag=False campaigns
        # keep the pre-Sprint-7 behavior byte-identical. On budget-exceeded we
        # log a degrade event but DO NOT abort the send — the LLM call that
        # produced this body already happened upstream (in the Claude
        # orchestrator), so refusing the SMTP send here just wastes tokens.
        budget_degraded = False
        if getattr(campaign, 'use_context_assembler', False):
            allowed, reason = ai_budget.check_budget_before_call(product.organization)
            if not allowed:
                budget_degraded = True
                self.stderr.write(self.style.WARNING(
                    f'  [budget] degrade: {reason} — proceeding with flat send'
                ))

        # 4. Resolve SMTP config with fallback to sibling campaigns in same product
        smtp_config = self._resolve_smtp_config(campaign, product)
        if not smtp_config:
            self.stderr.write(self.style.ERROR(
                f'EXIT 1: no MailboxConfig found for campaign "{campaign.name}" '
                f'or any sibling campaign in product "{product.slug}"'
            ))
            sys.exit(EXIT_GENERIC)

        # 5. SMTP send
        send_started = time.monotonic()
        try:
            result = EmailService.send_reply(
                to_email=inbound.from_email,
                subject=subject,
                body_html=body_html,
                in_reply_to=inbound.message_id,
                references=inbound.in_reply_to or inbound.message_id,
                from_email=smtp_config['email'],
                from_name=from_name,
                original_from=(f'{inbound.from_name} <{inbound.from_email}>'
                               if inbound.from_name else inbound.from_email),
                original_date=(inbound.received_at.strftime('%a, %d %b %Y %H:%M:%S')
                               if inbound.received_at else None),
                original_subject=inbound.subject,
                original_body_html=(inbound.body_text or '').replace('\n', '<br>'),
                smtp_config=smtp_config,
            )
        except Exception as e:
            self._increment_attempt(inbound)
            self._log_ai_usage(
                campaign, prospect, product, success=False,
                error_message=f'SMTP send failed: {e}',
                latency_ms=int((time.monotonic() - send_started) * 1000),
                word_count=word_count,
            )
            self.stderr.write(self.style.ERROR(f'EXIT 1: SMTP send failed: {e}'))
            sys.exit(EXIT_GENERIC)
        latency_ms = int((time.monotonic() - send_started) * 1000)

        if result.get('status') != 'sent':
            self._increment_attempt(inbound)
            self._log_ai_usage(
                campaign, prospect, product, success=False,
                error_message=f'EmailService returned non-sent status: {result}',
                latency_ms=latency_ms, word_count=word_count,
            )
            self.stderr.write(self.style.ERROR(f'EXIT 1: EmailService returned: {result}'))
            sys.exit(EXIT_GENERIC)

        # 6. Audit log row (only if prospect exists - EmailLog.prospect is required)
        if prospect:
            EmailLog.objects.create(
                campaign=campaign,
                prospect=prospect,
                to_email=inbound.from_email,
                subject=subject,
                body_html=body_html,
                sequence_number=0,
                template_name='ai_reply',
                status='sent',
                ses_message_id=result.get('message_id', ''),
                triggered_by='ai_reply',
            )
        else:
            self.stdout.write(self.style.WARNING(
                f'  No prospect linked to inbound {inbound.id} - skipping EmailLog audit row'
            ))

        # 7. Mark inbound replied + increment attempt
        inbound.replied = True
        inbound.auto_replied = True
        inbound.reply_sent_at = timezone.now()
        inbound.needs_reply = False
        inbound.ai_attempt_count = (inbound.ai_attempt_count or 0) + 1
        inbound.save(update_fields=[
            'replied', 'auto_replied', 'reply_sent_at',
            'needs_reply', 'ai_attempt_count', 'updated_at',
        ])

        # 8. AIUsageLog (success)
        self._log_ai_usage(
            campaign, prospect, product, success=True,
            latency_ms=latency_ms, word_count=word_count,
        )

        self.stdout.write(self.style.SUCCESS(
            f'EXIT 0: sent reply to {inbound.from_email} '
            f'({word_count} words, {latency_ms}ms SMTP, attempt #{inbound.ai_attempt_count})'
        ))
        sys.exit(EXIT_OK)

    # ------------------------------------------------------------------

    def _increment_attempt(self, inbound):
        """Bump ai_attempt_count without marking replied. Used on pre-send block / failure."""
        inbound.ai_attempt_count = (inbound.ai_attempt_count or 0) + 1
        inbound.save(update_fields=['ai_attempt_count', 'updated_at'])

    def _resolve_smtp_config(self, campaign, product):
        """Find an SMTP config for this campaign, falling back to sibling
        campaigns in the same product. Construction has no MailboxConfig of
        its own but Kingswood does and shares the same office@ mailbox -
        this fallback covers that case.
        """
        # 1. Direct lookup
        mb = MailboxConfig.objects.filter(campaign=campaign, is_active=True).first()
        if mb:
            return mb.get_smtp_config()
        # 2. Sibling campaign in same product
        mb = MailboxConfig.objects.filter(
            campaign__product_ref=product, is_active=True,
        ).first()
        if mb:
            return mb.get_smtp_config()
        return None

    def _resolve_brain_version(self, campaign, product):
        """Sprint 7 Phase 7.2.2 — look up the active brain_version for this
        product when the campaign is on the contextual path. Returns None on
        flag=False or when no ProductBrain row exists yet (avoids coupling
        the send path to brain seeding order).

        Also honors the PAPERCLIP_BRAIN_VERSION env var set by
        handle_replies._invoke_with_contextual_prompt so multi-hop subprocess
        invocations stay consistent even if DB read ordering differs.
        """
        if not getattr(campaign, 'use_context_assembler', False):
            return None
        import os as _os
        env_val = _os.environ.get('PAPERCLIP_BRAIN_VERSION')
        if env_val:
            try:
                return int(env_val)
            except ValueError:
                pass
        try:
            from campaigns.services.brain import load_brain_by_product
            return load_brain_by_product(product.slug).brain_version
        except Exception:
            return None

    def _log_ai_usage(self, campaign, prospect, product, *, success, latency_ms,
                      word_count=0, error_message=''):
        """Record this send attempt to AIUsageLog for cost/observability tracking.

        Note: token counts here are estimates - this command itself doesn't
        invoke the model. The Claude orchestrator that called this command
        does. We log a small fixed token cost for the send-time work
        (input prompt + body generation roughly attributed to this attempt).
        """
        if not (campaign and product and product.organization):
            return
        # Rough token estimate: body word count × 1.3 tokens/word for output,
        # plus a flat input cost for the system prompt context (~1500 tokens).
        # Real per-call tokens are tracked by the calling Claude session;
        # this row exists for per-persona attribution and quick "how much
        # did Lisa cost today" queries.
        estimated_input_tokens = 1500 + (word_count * 2)  # ctx + roughly-quoted inbound
        estimated_output_tokens = max(int(word_count * 1.3), 50)
        brain_version = self._resolve_brain_version(campaign, product)
        try:
            AIUsageLog.objects.create(
                organization=product.organization,
                product=product,
                campaign=campaign,
                prospect=prospect,
                feature='email_reply',
                model='claude-sonnet-4-6',
                input_tokens=estimated_input_tokens,
                output_tokens=estimated_output_tokens,
                cost_usd=self._estimate_cost(estimated_input_tokens, estimated_output_tokens),
                latency_ms=latency_ms,
                success=success,
                error_message=error_message,
                brain_version=brain_version,
            )
            # Sprint 7 Phase 7.2.2 — feed the atomic org counter used by
            # ai_budget.check_budget_before_call(). Only charge on successful
            # sends; failures are not billable.
            if success and getattr(campaign, 'use_context_assembler', False):
                cost_cents = int(
                    self._estimate_cost(estimated_input_tokens, estimated_output_tokens) * 100
                )
                if cost_cents > 0:
                    ai_budget.record_cost(product.organization, cents=cost_cents)
        except Exception as e:
            # Never let usage logging fail the actual send
            self.stderr.write(self.style.WARNING(f'AIUsageLog write failed: {e}'))

    @staticmethod
    def _estimate_cost(input_tokens, output_tokens):
        """Sonnet 4.6 pricing: $3/M input, $15/M output."""
        from decimal import Decimal
        input_cost = Decimal('3.00') * Decimal(input_tokens) / Decimal('1000000')
        output_cost = Decimal('15.00') * Decimal(output_tokens) / Decimal('1000000')
        return (input_cost + output_cost).quantize(Decimal('0.0001'))
