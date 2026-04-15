"""F4 — unit tests for `match_inbound_to_prospect` tenant isolation.

These tests prove the F1 fix is correct:

  - Thread ancestor beats any email match, even when the email match would
    land in a different tenant.
  - Mailbox product floor prevents cross-product bleed on email-only match.
  - Ambiguous matches (>1 prospect for same email, no thread ancestor) are
    flagged for manual review instead of guessing.
  - Single-tenant no-collision case still matches cleanly.

Uses Django TestCase so fixtures live in an isolated test DB and are torn
down automatically. Safe to run against production Postgres because it
never touches the real `campaigns` tables.

Run:
    venv/bin/python manage.py test campaigns.tests.test_reply_matching -v 2
"""
from datetime import datetime, timezone as dt_timezone

from django.test import TestCase

from campaigns.management.commands.check_replies import match_inbound_to_prospect
from campaigns.models import (
    Campaign,
    EmailLog,
    Organization,
    Product,
    Prospect,
)


class ReplyMatchingTenantIsolationTests(TestCase):
    """The bug this suite guards against:

    Alex (info@printpoint.ie) exists as a prospect in TWO campaigns across
    TWO products — a TaggIQ Ireland campaign and an FP Dublin BNI campaign.
    When Alex replies to an FP BNI intro email, the old `check_replies`
    matching picked whichever prospect row `.first()` returned (arbitrary,
    effectively the lowest PK), which was TaggIQ. The reply then got routed
    through the TaggIQ PromptTemplate and an AI-generated TaggIQ POS pitch
    went out in an FP franchise BNI thread.

    Post-F1, the ordering is:
      1. In-Reply-To thread ancestor (unambiguous: points back to the exact
         outbound EmailLog which has a definitive campaign FK)
      2. Mailbox-scoped email match within the Product floor
      3. Global fallback only when no floor is known
      4. Ambiguous >1 matches never auto-match — returned as needs_manual_review
    """

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(
            name='Skillblend Ltd',
            slug='skillblend-test',
        )
        cls.taggiq = Product.objects.create(
            organization=cls.org,
            name='TaggIQ',
            slug='taggiq-test',
        )
        cls.fullypromoted = Product.objects.create(
            organization=cls.org,
            name='Fully Promoted Ireland',
            slug='fullypromoted-test',
        )

        cls.tq_campaign = Campaign.objects.create(
            name='TaggIQ Ireland Print & Promo TEST',
            product='print-promo',
            product_ref=cls.taggiq,
            from_email='prakash@taggiq.test',
            from_name='Prakash',
        )
        cls.fp_campaign = Campaign.objects.create(
            name='FP Dublin BNI Print & Promo TEST',
            product='franchise',
            product_ref=cls.fullypromoted,
            from_email='prakash@fullypromoted.test',
            from_name='Prakash',
        )
        cls.fp_other_campaign = Campaign.objects.create(
            name='FP Ireland Franchise Recruitment TEST',
            product='franchise',
            product_ref=cls.fullypromoted,
            from_email='prakash@fullypromoted.test',
            from_name='Prakash',
        )

        # Alex exists as a prospect in BOTH TaggIQ and FP — the collision
        # case that triggered the original bug.
        cls.tq_alex = Prospect.objects.create(
            campaign=cls.tq_campaign,
            business_name='Printpoint Ireland (TaggIQ row)',
            email='alex@printpoint.test',
            decision_maker_name='Alex OBrien',
            status='contacted',
        )
        cls.fp_alex = Prospect.objects.create(
            campaign=cls.fp_campaign,
            business_name='Printpoint Ireland (FP row)',
            email='alex@printpoint.test',
            decision_maker_name='Alex OBrien',
            status='contacted',
        )

        # Someone who exists in only ONE campaign — the happy path.
        cls.solo_prospect = Prospect.objects.create(
            campaign=cls.fp_campaign,
            business_name='SoloShop',
            email='solo@example.test',
            decision_maker_name='Solo Person',
            status='contacted',
        )

        # Outbound EmailLog from FP campaign → Alex with a known SES id.
        # This is the thread ancestor we thread the inbound's In-Reply-To back to.
        cls.fp_outbound = EmailLog.objects.create(
            campaign=cls.fp_campaign,
            prospect=cls.fp_alex,
            to_email='alex@printpoint.test',
            subject='Intro email Alex & Prakash',
            body_html='<p>Hi Alex, nice to meet you via Padraig.</p>',
            sequence_number=1,
            template_name='test_intro',
            status='sent',
            ses_message_id='0102019abcdef1234567890-test-ses-id-001',
            triggered_by='send_sequences',
        )

    # ------------------------------------------------------------------
    # Rule 1 — thread ancestor wins, even when email-only would pick wrong
    # ------------------------------------------------------------------

    def test_thread_ancestor_beats_cross_product_email_collision(self):
        """The regression test for the actual bug Prakash saw today.

        Setup: Alex exists in both TaggIQ and FP. Inbound arrives with an
        `In-Reply-To` header whose local-part matches the FP outbound's
        ses_message_id. Old code picked TaggIQ (lowest PK). Fixed code
        threads through the EmailLog and returns the FP row.
        """
        prospect, source, ambiguous = match_inbound_to_prospect(
            from_email='alex@printpoint.test',
            from_name='Alex OBrien',
            in_reply_to='<0102019abcdef1234567890-test-ses-id-001@eu-west-1.amazonses.com>',
            mailbox_campaign=None,
            mailbox_campaigns=[self.fp_campaign, self.fp_other_campaign],
            product_floor=self.fullypromoted,
        )

        self.assertFalse(ambiguous, 'thread ancestor path must not flag ambiguous')
        self.assertIsNotNone(prospect)
        self.assertEqual(prospect.id, self.fp_alex.id,
                         'matched prospect must be the FP row, not the TaggIQ row')
        self.assertEqual(source, 'thread_ancestor')

    def test_thread_ancestor_wins_even_against_mismatched_product_floor(self):
        """If an operator misconfigures a mailbox so the product floor is
        wrong (e.g., TaggIQ product floor but the actual thread is FP),
        the thread ancestor still wins. This prevents a misconfiguration
        from silently cross-tenant-routing a reply.
        """
        prospect, source, _ = match_inbound_to_prospect(
            from_email='alex@printpoint.test',
            from_name='Alex OBrien',
            in_reply_to='<0102019abcdef1234567890-test-ses-id-001@eu-west-1.amazonses.com>',
            mailbox_campaign=self.tq_campaign,  # WRONG floor
            mailbox_campaigns=[self.tq_campaign],
            product_floor=self.taggiq,          # WRONG floor
        )
        self.assertEqual(source, 'thread_ancestor')
        self.assertEqual(prospect.id, self.fp_alex.id)

    # ------------------------------------------------------------------
    # Rule 2 — mailbox-scoped email match when no thread ancestor exists
    # ------------------------------------------------------------------

    def test_product_floor_scopes_email_match_to_correct_tenant(self):
        """No In-Reply-To. Alex exists in both products. Mailbox has an
        FP product floor. Must match FP row, not TaggIQ.
        """
        prospect, source, ambiguous = match_inbound_to_prospect(
            from_email='alex@printpoint.test',
            from_name='Alex OBrien',
            in_reply_to='',  # no thread ancestor
            mailbox_campaign=None,
            mailbox_campaigns=[self.fp_campaign, self.fp_other_campaign],
            product_floor=self.fullypromoted,
        )
        self.assertFalse(ambiguous)
        self.assertIsNotNone(prospect)
        self.assertEqual(prospect.id, self.fp_alex.id)
        self.assertEqual(source, 'email_scoped')

    def test_ambiguous_when_two_prospects_match_within_mailbox_boundary(self):
        """If two prospect rows share the same email AND both are within
        the mailbox boundary (same Product) AND no thread ancestor exists,
        the match returns ambiguous=True with prospect=None. The caller
        then saves the inbound as needs_manual_review.
        """
        # Create a second FP prospect with the same email so the scoped
        # lookup returns 2 rows.
        Prospect.objects.create(
            campaign=self.fp_other_campaign,
            business_name='Printpoint (second FP row)',
            email='alex@printpoint.test',
            decision_maker_name='Alex OBrien',
            status='contacted',
        )
        prospect, source, ambiguous = match_inbound_to_prospect(
            from_email='alex@printpoint.test',
            from_name='Alex OBrien',
            in_reply_to='',
            mailbox_campaign=None,
            mailbox_campaigns=[self.fp_campaign, self.fp_other_campaign],
            product_floor=self.fullypromoted,
        )
        self.assertTrue(ambiguous)
        self.assertIsNone(prospect)
        self.assertEqual(source, 'ambiguous_scoped')

    def test_product_floor_blocks_cross_product_bleed_on_zero_match(self):
        """If the mailbox has an FP product floor but Alex only exists as a
        TaggIQ prospect (hypothetical: FP row gets deleted), the match
        returns 0 inside FP. The global fallback MUST NOT run — reaching
        into TaggIQ would be a cross-product bleed. Expect no match.
        """
        # Delete the FP prospect so only TaggIQ remains
        self.fp_alex.delete()

        prospect, source, ambiguous = match_inbound_to_prospect(
            from_email='alex@printpoint.test',
            from_name='Alex OBrien',
            in_reply_to='',
            mailbox_campaign=None,
            mailbox_campaigns=[self.fp_campaign, self.fp_other_campaign],
            product_floor=self.fullypromoted,
        )
        # No prospect, no ambiguity. Matching should stop at the product
        # floor and refuse to fall through globally.
        self.assertFalse(ambiguous)
        self.assertIsNone(prospect,
            'product floor must block cross-product bleed even on 0 matches')
        self.assertEqual(source, 'no_match')

    # ------------------------------------------------------------------
    # Rule 3 — global fallback only when no floor AND single match
    # ------------------------------------------------------------------

    def test_global_fallback_single_match(self):
        """No product floor, no thread ancestor, single global match → OK.
        This is the legacy happy path and must still work.
        """
        prospect, source, _ = match_inbound_to_prospect(
            from_email='solo@example.test',
            from_name='Solo Person',
            in_reply_to='',
            mailbox_campaign=None,
            mailbox_campaigns=[],
            product_floor=None,
        )
        self.assertIsNotNone(prospect)
        self.assertEqual(prospect.id, self.solo_prospect.id)
        self.assertEqual(source, 'email_global')

    def test_global_fallback_ambiguous_with_multiple_products(self):
        """No product floor, no thread ancestor, >1 prospects across
        products → ambiguous, manual review required.
        """
        prospect, source, ambiguous = match_inbound_to_prospect(
            from_email='alex@printpoint.test',
            from_name='Alex OBrien',
            in_reply_to='',
            mailbox_campaign=None,
            mailbox_campaigns=[],
            product_floor=None,
        )
        self.assertTrue(ambiguous)
        self.assertIsNone(prospect)
        self.assertEqual(source, 'ambiguous_global')

    # ------------------------------------------------------------------
    # Sanity — no inputs returns no match, never raises
    # ------------------------------------------------------------------

    def test_no_inputs_returns_no_match_not_crash(self):
        prospect, source, ambiguous = match_inbound_to_prospect(
            from_email='nobody@nowhere.test',
            from_name='',
            in_reply_to='',
            mailbox_campaign=None,
            mailbox_campaigns=[],
            product_floor=None,
        )
        self.assertIsNone(prospect)
        self.assertFalse(ambiguous)
        self.assertEqual(source, 'no_match')
