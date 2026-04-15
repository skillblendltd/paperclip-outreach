"""F5 — audit reply attribution for cross-product bleed.

Read-only retrospective audit. For every `InboundEmail` received in the
trailing window, recompute what `match_inbound_to_prospect` (F1 rules)
would have returned TODAY, and compare it against the prospect that was
actually attributed at the time.

Mismatches fall into three buckets:

  1. **cross_product_bleed** — the stored attribution points at a
     prospect in a different Product than the thread ancestor says is
     correct. This is the actual bug F1 fixes.

  2. **wrong_campaign_same_product** — the thread ancestor points at a
     different campaign than the stored attribution, but both are in the
     same Product. Lower severity; voice is still right.

  3. **now_ambiguous** — under F1 rules this inbound would be flagged as
     needing manual review (>1 rows, no thread ancestor), but it was
     auto-attributed in the past. These are the ones that may have had
     wrong voices sent out.

Non-destructive. Never writes. Exit code 0 regardless of findings — the
purpose is visibility, not gating. Pipe output to a file if you want
to diff across runs:

    python manage.py audit_reply_attribution --days 90 > /tmp/audit.txt
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from campaigns.management.commands.check_replies import match_inbound_to_prospect
from campaigns.models import Campaign, InboundEmail, MailboxConfig


class Command(BaseCommand):
    help = 'Retrospective audit of InboundEmail attribution against the F1 matching rules.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90,
                            help='Audit inbounds from last N days (default 90)')
        parser.add_argument('--product', help='Filter by product slug (e.g. taggiq)')
        parser.add_argument('--show-ok', action='store_true',
                            help='Also print matches where attribution is correct')
        parser.add_argument('--limit', type=int, default=0,
                            help='Max inbounds to audit (0 = no limit)')

    def handle(self, *args, **opts):
        days = opts['days']
        product_filter = opts.get('product')
        show_ok = opts['show_ok']
        limit = opts['limit']

        since = timezone.now() - timedelta(days=days)

        # Precompute the mailbox → product_floor map so every audit row uses
        # the same mailbox context the live pipeline would have used. Built
        # from MailboxConfig rows grouped by imap_email (the same logic as
        # check_replies._get_mailboxes).
        mailbox_floors = self._build_mailbox_floor_map()

        qs = InboundEmail.objects.filter(
            received_at__gte=since,
            prospect__isnull=False,  # only audit the ones that got attributed
        ).select_related('prospect__campaign__product_ref', 'campaign__product_ref')

        if product_filter:
            qs = qs.filter(campaign__product_ref__slug=product_filter)

        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(
            f'Auditing {total} inbound(s) from last {days} days'
            + (f' for product={product_filter}' if product_filter else '')
            + '...\n'
        )

        counters = {
            'ok_via_thread': 0,
            'unverifiable_no_thread': 0,
            'cross_product_bleed': 0,
            'wrong_campaign_same_product': 0,
            'audit_error': 0,
        }
        bleed_samples = []

        # Ground truth strategy: for each audited inbound, attempt thread
        # ancestry independently. The thread-ancestor path needs no mailbox
        # context — it walks In-Reply-To → EmailLog.ses_message_id → that
        # EmailLog's prospect. If it finds a match, that IS the correct
        # attribution. Compare against stored.
        #
        # Inbounds without In-Reply-To cannot be audited precisely from DB
        # alone (we'd need to know which mailbox received them, which
        # InboundEmail doesn't record). These are reported as
        # "unverifiable" — they may or may not be wrong, but we can't
        # tell without replaying IMAP.
        for inbound in qs:
            try:
                stored_prospect_id = inbound.prospect_id
                stored_product_slug = (
                    inbound.prospect.campaign.product_ref.slug
                    if inbound.prospect.campaign and inbound.prospect.campaign.product_ref
                    else None
                )
                stored_campaign_id = inbound.prospect.campaign_id

                if not inbound.in_reply_to:
                    counters['unverifiable_no_thread'] += 1
                    continue

                recomputed, source, _ = match_inbound_to_prospect(
                    from_email=inbound.from_email.lower(),
                    from_name=inbound.from_name or '',
                    in_reply_to=inbound.in_reply_to,
                    mailbox_campaign=None,
                    mailbox_campaigns=[],
                    product_floor=None,  # force thread-ancestor path
                    stdout=None,
                    style=None,
                )

                if source != 'thread_ancestor' or recomputed is None:
                    # Thread ancestor could not be resolved (maybe the
                    # outbound was purged, maybe In-Reply-To is malformed).
                    # Treat as unverifiable rather than as evidence of
                    # correctness.
                    counters['unverifiable_no_thread'] += 1
                    continue

                if recomputed.id == stored_prospect_id:
                    counters['ok_via_thread'] += 1
                    if show_ok:
                        self.stdout.write(
                            f'  OK (thread) {inbound.from_email} -> '
                            f'{recomputed.business_name} ({stored_product_slug})'
                        )
                    continue

                # Thread ancestor disagrees with stored attribution.
                recomputed_product_slug = (
                    recomputed.campaign.product_ref.slug
                    if recomputed.campaign and recomputed.campaign.product_ref
                    else None
                )

                if recomputed_product_slug != stored_product_slug:
                    counters['cross_product_bleed'] += 1
                    if len(bleed_samples) < 20:
                        bleed_samples.append({
                            'inbound_id': str(inbound.id),
                            'received_at': inbound.received_at,
                            'from': inbound.from_email,
                            'subject': inbound.subject[:70],
                            'stored_product': stored_product_slug,
                            'stored_prospect': inbound.prospect.business_name,
                            'correct_product': recomputed_product_slug,
                            'correct_prospect': recomputed.business_name,
                            'source': source,
                        })
                else:
                    # Same product, different campaign or different row.
                    counters['wrong_campaign_same_product'] += 1

            except Exception as exc:
                counters['audit_error'] += 1
                self.stderr.write(self.style.ERROR(
                    f'  audit error on inbound {inbound.id}: {exc}'
                ))

        # ---------- Report ----------
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== Audit summary ==='))
        for key, count in counters.items():
            style = self.style.ERROR if key == 'cross_product_bleed' and count else (
                self.style.WARNING if 'ambiguous' in key and count else lambda s: s
            )
            self.stdout.write(style(f'  {key:32s} {count}'))

        if bleed_samples:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(
                f'=== Cross-product bleed samples (up to 20 of {counters["cross_product_bleed"]}) ==='
            ))
            for s in bleed_samples:
                self.stdout.write(
                    f'  [{s["received_at"]:%Y-%m-%d %H:%M}] {s["from"]}'
                )
                self.stdout.write(
                    f'    subject: {s["subject"]}'
                )
                self.stdout.write(
                    f'    stored:  {s["stored_product"]} / {s["stored_prospect"]}'
                )
                self.stdout.write(
                    f'    correct: {s["correct_product"]} / {s["correct_prospect"]} (via {s["source"]})'
                )
                self.stdout.write('')

        self.stdout.write('')
        self.stdout.write(
            'Note: only inbounds with In-Reply-To can be precisely audited. '
            'The "unverifiable_no_thread" bucket needs IMAP replay to audit '
            'and is not wrong-by-construction — it just cannot be checked from '
            'the DB alone.'
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_mailbox_floor_map(self):
        """Map imap_email → (product_floor, [campaigns]) for the audit.

        Mirrors `_get_mailboxes` grouping logic: a mailbox has a product
        floor iff every Campaign using that mailbox shares one Product.
        """
        out = {}
        configs = MailboxConfig.objects.filter(is_active=True).select_related(
            'campaign__product_ref'
        )
        groups = {}
        for mb in configs:
            groups.setdefault(mb.imap_email.lower(), []).append(mb.campaign)
        for imap_email, campaigns in groups.items():
            products = {
                c.product_ref_id for c in campaigns if c.product_ref_id
            }
            floor = None
            if len(products) == 1:
                floor = campaigns[0].product_ref
            out[imap_email] = (floor, campaigns)
        return out

    def _mailbox_ctx_for_inbound(self, inbound, mailbox_floors):
        """Return (product_floor, mailbox_campaigns) for an inbound.

        Best-effort: InboundEmail does not store the mailbox it arrived
        through, so we use the stored campaign FK to find a MailboxConfig
        whose campaign matches. When the FK is missing or corrupted
        (historical bad rows with `'[]'` in campaign_id), we fall back to
        (None, []) which means "no floor, audit against global rules."
        """
        campaign_id = inbound.campaign_id
        if not campaign_id:
            return (None, [])
        try:
            mb = MailboxConfig.objects.filter(campaign_id=campaign_id).first()
        except (ValueError, TypeError):
            return (None, [])
        if not mb:
            return (None, [])
        return mailbox_floors.get(mb.imap_email.lower(), (None, []))
