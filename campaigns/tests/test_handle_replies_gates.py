"""G5 — unit tests for handle_replies._filter_actionable_inbounds gates.

Exercises the 3 safety gates (reply window / grace window / unread
cross-check) without real IMAP. The IMAP probe is mocked via
monkeypatching the `_imap_fetch_unseen_message_ids` method on the
Command instance, so each test controls exactly what the "mailbox"
returns.
"""
from datetime import timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from campaigns.management.commands.handle_replies import Command as HandleRepliesCommand
from campaigns.models import (
    Campaign,
    InboundEmail,
    MailboxConfig,
    Organization,
    Product,
    Prospect,
)


def _open_window(campaign):
    """Helper: set a 24/7 reply window so gate 1 never fires."""
    campaign.reply_window_start_hour = 0
    campaign.reply_window_end_hour = 24
    campaign.reply_window_days = '0,1,2,3,4,5,6'
    campaign.save(update_fields=[
        'reply_window_start_hour', 'reply_window_end_hour',
        'reply_window_days', 'updated_at',
    ])


class HandleRepliesFilterGateTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Test', slug='test-org-gates')
        cls.product = Product.objects.create(
            organization=cls.org, name='Gates', slug='gates-product',
        )
        cls.campaign = Campaign.objects.create(
            name='Gate Test Campaign',
            product='other',
            product_ref=cls.product,
            from_email='gate@example.test',
            from_name='Gate Test',
        )
        cls.mailbox = MailboxConfig.objects.create(
            campaign=cls.campaign,
            imap_email='gate-inbox@example.test',
            imap_host='imap.example.test',
            imap_port=993,
            imap_password='test',
            smtp_email='gate-inbox@example.test',
            smtp_host='smtp.example.test',
            smtp_port=465,
            smtp_password='test',
            is_active=True,
        )

    def _mk_cmd(self, unseen_ids_return):
        cmd = HandleRepliesCommand()
        cmd.stdout = MagicMock()
        cmd.stderr = MagicMock()
        cmd.style = MagicMock()
        cmd.style.WARNING = lambda s: s
        cmd.style.SUCCESS = lambda s: s
        cmd.style.ERROR = lambda s: s
        cmd._imap_fetch_unseen_message_ids = MagicMock(return_value=set(unseen_ids_return))
        return cmd

    def _mk_prospect(self, email='p@example.test'):
        return Prospect.objects.create(
            campaign=self.campaign,
            business_name='Biz',
            email=email,
            status='contacted',
        )

    def _mk_inbound(self, prospect, msg_id, age_minutes=10, classification='interested'):
        inbound = InboundEmail.objects.create(
            prospect=prospect,
            campaign=self.campaign,
            from_email=prospect.email,
            from_name='Test',
            subject=f'Test {msg_id}',
            body_text='hello',
            message_id=msg_id,
            classification=classification,
            needs_reply=True,
            received_at=timezone.now() - timedelta(minutes=age_minutes),
        )
        past = timezone.now() - timedelta(minutes=age_minutes)
        type(inbound).objects.filter(pk=inbound.pk).update(created_at=past)
        inbound.refresh_from_db()
        return inbound

    # ------------------------------------------------------------------
    # Gate 1: reply window
    # ------------------------------------------------------------------

    def test_gate_skips_when_campaign_outside_reply_window(self):
        """Force 23-00 1-hour window. Unless test runs at 23:xx Dublin,
        gate 1 must fire and drop the inbound."""
        self.campaign.reply_window_start_hour = 23
        self.campaign.reply_window_end_hour = 0
        self.campaign.save(update_fields=[
            'reply_window_start_hour', 'reply_window_end_hour', 'updated_at'])
        p = self._mk_prospect('window-skip@example.test')
        inbound = self._mk_inbound(p, '<win-1@x>', age_minutes=10)

        cmd = self._mk_cmd(unseen_ids_return=[inbound.message_id])
        actionable = cmd._filter_actionable_inbounds([inbound])

        dublin_hour = timezone.now().astimezone(ZoneInfo('Europe/Dublin')).hour
        if dublin_hour != 23:
            self.assertEqual(len(actionable), 0)

    def test_gate_passes_when_window_covers_all_day(self):
        _open_window(self.campaign)
        p = self._mk_prospect('window-pass@example.test')
        inbound = self._mk_inbound(p, '<win-2@x>', age_minutes=10)

        cmd = self._mk_cmd(unseen_ids_return=[inbound.message_id])
        actionable = cmd._filter_actionable_inbounds([inbound])

        self.assertEqual(len(actionable), 1)
        self.assertEqual(actionable[0].id, inbound.id)

    # ------------------------------------------------------------------
    # Gate 2: grace window
    # ------------------------------------------------------------------

    def test_gate_skips_inbound_within_grace_window(self):
        _open_window(self.campaign)
        self.campaign.reply_grace_minutes = 5
        self.campaign.save(update_fields=['reply_grace_minutes', 'updated_at'])
        p = self._mk_prospect('grace-skip@example.test')
        inbound = self._mk_inbound(p, '<grace-1@x>', age_minutes=2)

        cmd = self._mk_cmd(unseen_ids_return=[inbound.message_id])
        actionable = cmd._filter_actionable_inbounds([inbound])

        self.assertEqual(len(actionable), 0,
            '2-min-old inbound must be skipped when grace is 5 min')

    def test_gate_passes_inbound_past_grace_window(self):
        _open_window(self.campaign)
        self.campaign.reply_grace_minutes = 5
        self.campaign.save(update_fields=['reply_grace_minutes', 'updated_at'])
        p = self._mk_prospect('grace-pass@example.test')
        inbound = self._mk_inbound(p, '<grace-2@x>', age_minutes=10)

        cmd = self._mk_cmd(unseen_ids_return=[inbound.message_id])
        actionable = cmd._filter_actionable_inbounds([inbound])

        self.assertEqual(len(actionable), 1)

    def test_gate_configurable_grace_per_campaign(self):
        _open_window(self.campaign)
        self.campaign.reply_grace_minutes = 15
        self.campaign.save(update_fields=['reply_grace_minutes', 'updated_at'])
        p = self._mk_prospect('grace-long@example.test')
        inbound = self._mk_inbound(p, '<grace-3@x>', age_minutes=10)

        cmd = self._mk_cmd(unseen_ids_return=[inbound.message_id])
        actionable = cmd._filter_actionable_inbounds([inbound])

        self.assertEqual(len(actionable), 0,
            '10min-old inbound must be skipped when campaign grace is 15min')

    # ------------------------------------------------------------------
    # Gate 3: unread cross-check
    # ------------------------------------------------------------------

    def test_gate_skips_inbound_claimed_by_human_without_mutating(self):
        """SEEN-in-mailbox inbound is skipped this tick but needs_reply stays
        True, so the operator can mark the email back to UNSEEN on their phone
        and the AI will pick it up on the next tick."""
        _open_window(self.campaign)
        p = self._mk_prospect('claimed@example.test')
        inbound = self._mk_inbound(p, '<claim-1@x>', age_minutes=10)

        cmd = self._mk_cmd(unseen_ids_return=set())
        actionable = cmd._filter_actionable_inbounds([inbound])

        self.assertEqual(len(actionable), 0)
        inbound.refresh_from_db()
        self.assertTrue(inbound.needs_reply,
            'needs_reply must remain True so a future unread-flip releases it')

    def test_gate_releases_inbound_when_marked_unread_again(self):
        """Round-trip: tick 1 sees SEEN and skips, tick 2 sees UNSEEN (operator
        flipped it) and lets the AI through."""
        _open_window(self.campaign)
        p = self._mk_prospect('flip-back@example.test')
        inbound = self._mk_inbound(p, '<flip-1@x>', age_minutes=10)

        cmd_seen = self._mk_cmd(unseen_ids_return=set())
        self.assertEqual(len(cmd_seen._filter_actionable_inbounds([inbound])), 0)

        cmd_unseen = self._mk_cmd(unseen_ids_return={inbound.message_id})
        actionable = cmd_unseen._filter_actionable_inbounds([inbound])
        self.assertEqual(len(actionable), 1,
            'After operator marks unread again, AI must pick it up')

    def test_gate_passes_inbound_still_unseen(self):
        _open_window(self.campaign)
        p = self._mk_prospect('still-unseen@example.test')
        inbound = self._mk_inbound(p, '<unseen-1@x>', age_minutes=10)

        cmd = self._mk_cmd(unseen_ids_return={inbound.message_id})
        actionable = cmd._filter_actionable_inbounds([inbound])

        self.assertEqual(len(actionable), 1)

    def test_gate_fails_open_on_imap_error(self):
        """IMAP outage must not silently block all replies."""
        _open_window(self.campaign)
        p = self._mk_prospect('imap-down@example.test')
        inbound = self._mk_inbound(p, '<imap-err-1@x>', age_minutes=10)

        cmd = HandleRepliesCommand()
        cmd.stdout = MagicMock()
        cmd.stderr = MagicMock()
        cmd.style = MagicMock()
        cmd.style.WARNING = lambda s: s
        cmd.style.SUCCESS = lambda s: s
        cmd.style.ERROR = lambda s: s
        cmd._imap_fetch_unseen_message_ids = MagicMock(
            side_effect=ConnectionError('IMAP timeout'))

        actionable = cmd._filter_actionable_inbounds([inbound])

        self.assertEqual(len(actionable), 1,
            'Fail-open: IMAP errors must not silently block replies')

    # ------------------------------------------------------------------
    # Combined: real-world mixed batch
    # ------------------------------------------------------------------

    def test_mixed_batch_only_eligible_passes(self):
        """Realistic batch: 4 inbounds — one fresh (grace skip), one
        claimed (unread skip), one past grace still unseen (pass), one
        past grace claimed (skip). Only one survives."""
        _open_window(self.campaign)
        self.campaign.reply_grace_minutes = 5
        self.campaign.save(update_fields=['reply_grace_minutes', 'updated_at'])

        p = self._mk_prospect('mixed-batch@example.test')

        fresh = self._mk_inbound(p, '<fresh@x>', age_minutes=2)       # grace skip
        claimed_old = self._mk_inbound(p, '<claimed-old@x>', age_minutes=10)  # unread skip
        eligible = self._mk_inbound(p, '<eligible@x>', age_minutes=10)  # pass
        claimed_old2 = self._mk_inbound(p, '<claimed-old-2@x>', age_minutes=20)  # unread skip

        # Only <eligible@x> is still unseen; the two "claimed_old" ones are seen
        cmd = self._mk_cmd(unseen_ids_return={eligible.message_id, fresh.message_id})
        actionable = cmd._filter_actionable_inbounds([
            fresh, claimed_old, eligible, claimed_old2,
        ])

        # Only eligible survives
        self.assertEqual(len(actionable), 1)
        self.assertEqual(actionable[0].id, eligible.id)

        # fresh stays needs_reply=True (skipped but will retry next tick)
        fresh.refresh_from_db()
        self.assertTrue(fresh.needs_reply,
            'Grace-window skip must not flip needs_reply — will retry later')

        # claimed_old and claimed_old2 stay needs_reply=True (skipped this tick
        # but releasable — operator marks them unread and the next tick picks up)
        claimed_old.refresh_from_db()
        claimed_old2.refresh_from_db()
        self.assertTrue(claimed_old.needs_reply)
        self.assertTrue(claimed_old2.needs_reply)
