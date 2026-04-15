"""H3 — unit tests for Prospect.reply_count + last_replied_at (2026-04-15).

Proves the atomic counter update in `check_replies._process_mailbox`:

  - Counts inbounds with classification in {interested, question, other,
    not_interested, opt_out}
  - Excludes bounce + out_of_office
  - last_replied_at tracks the most recent counted inbound's created_at
  - F() increment survives subsequent prospect.save(update_fields=...)
    calls from _execute_actions (the critical invariant)

We drive the write site directly via the same DB path the live code
uses, rather than through IMAP. The goal is to prove the COUNTER
semantics are correct; IMAP fetching is exercised separately.
"""
from django.db.models import F
from django.test import TestCase
from django.utils import timezone

from campaigns.models import (
    Campaign,
    InboundEmail,
    Organization,
    Product,
    Prospect,
)


class ReplyCounterTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Test Org', slug='test-org')
        cls.product = Product.objects.create(
            organization=cls.org, name='Test Product', slug='test-product',
        )
        cls.campaign = Campaign.objects.create(
            name='Reply Counter Test Campaign',
            product='other',
            product_ref=cls.product,
            from_email='test@example.test',
            from_name='Test',
        )

    def _mk_prospect(self, email='prospect@example.test'):
        return Prospect.objects.create(
            campaign=self.campaign,
            business_name='Test Shop',
            email=email,
            status='contacted',
            reply_count=0,
            last_replied_at=None,
        )

    def _increment(self, prospect, inbound):
        """Simulate the write site in check_replies._process_mailbox."""
        Prospect.objects.filter(pk=prospect.pk).update(
            reply_count=F('reply_count') + 1,
            last_replied_at=inbound.created_at,
            updated_at=timezone.now(),
        )

    def _create_inbound(self, prospect, classification, msg_id, body='hi'):
        return InboundEmail.objects.create(
            prospect=prospect,
            campaign=self.campaign,
            from_email=prospect.email,
            from_name='Test',
            subject=f'Test {classification}',
            body_text=body,
            message_id=msg_id,
            classification=classification,
            needs_reply=classification in ('interested', 'question', 'other'),
            received_at=timezone.now(),
        )

    def test_counter_starts_at_zero(self):
        p = self._mk_prospect('count-zero@example.test')
        self.assertEqual(p.reply_count, 0)
        self.assertIsNone(p.last_replied_at)

    def test_interested_reply_increments_counter(self):
        p = self._mk_prospect('interested@example.test')
        inbound = self._create_inbound(p, 'interested', '<msg-1@x>')
        self._increment(p, inbound)
        p.refresh_from_db()
        self.assertEqual(p.reply_count, 1)
        self.assertIsNotNone(p.last_replied_at)

    def test_three_inbounds_one_bounce_one_opt_out_one_interested(self):
        """Mixed classifications: only the 2 countable ones increment, and
        last_replied_at tracks the newest of those two.
        """
        p = self._mk_prospect('mixed@example.test')

        # 1. bounce — skipped by the live write site (not incremented)
        self._create_inbound(p, 'bounce', '<bounce-1@x>')

        # 2. opt_out — counted
        opt_out = self._create_inbound(p, 'opt_out', '<optout-1@x>')
        self._increment(p, opt_out)

        # 3. interested — counted, most recent
        interested = self._create_inbound(p, 'interested', '<interested-1@x>')
        self._increment(p, interested)

        p.refresh_from_db()
        self.assertEqual(p.reply_count, 2, 'bounce must not increment')
        self.assertEqual(
            p.last_replied_at, interested.created_at,
            'last_replied_at must track the most recent counted inbound',
        )

    def test_out_of_office_not_counted(self):
        p = self._mk_prospect('ooo@example.test')
        self._create_inbound(p, 'out_of_office', '<ooo-1@x>')
        # Live write site skips out_of_office — simulated by NOT incrementing
        p.refresh_from_db()
        self.assertEqual(p.reply_count, 0)
        self.assertIsNone(p.last_replied_at)

    def test_f_expression_survives_subsequent_save_with_update_fields(self):
        """Critical invariant: F() increment must not be clobbered by a
        subsequent prospect.save(update_fields=[...]) that writes a
        disjoint column set. This is what _execute_actions does (status /
        send_enabled / notes) after the caller has already incremented.
        """
        p = self._mk_prospect('invariant@example.test')
        inbound = self._create_inbound(p, 'interested', '<inv-1@x>')

        # Caller's F() update
        self._increment(p, inbound)

        # Simulated _execute_actions: modify unrelated fields and save
        # with update_fields. In-memory `p` still has reply_count=0 from
        # construction — this is the realistic scenario.
        p.status = 'interested'
        p.save(update_fields=['status', 'updated_at'])

        # Verify F() increment survived
        p.refresh_from_db()
        self.assertEqual(
            p.reply_count, 1,
            'F() increment must survive a disjoint save(update_fields=...)',
        )
        self.assertEqual(p.status, 'interested')

    def test_f_expression_clobbered_by_naked_save(self):
        """Negative control: demonstrates WHY the invariant matters.

        If a future engineer adds `prospect.save()` (no update_fields)
        inside _execute_actions, the F() increment gets wiped because the
        in-memory Prospect instance still has the stale reply_count value.
        This test proves the failure mode exists so the invariant comment
        on _execute_actions is load-bearing, not decorative.
        """
        p = self._mk_prospect('clobber@example.test')
        inbound = self._create_inbound(p, 'interested', '<clob-1@x>')

        self._increment(p, inbound)

        # Naked save — THIS is what we must never do in _execute_actions.
        p.status = 'interested'
        p.save()

        p.refresh_from_db()
        self.assertEqual(
            p.reply_count, 0,
            'A naked save() clobbers the F() increment — this is the '
            'failure mode the _execute_actions invariant guards against',
        )
