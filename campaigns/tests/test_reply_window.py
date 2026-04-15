"""G2 — unit tests for reply_window.is_within_reply_window.

Proves the business-hours gate behaves correctly across:
  - in-window weekday
  - out-of-window weekday (too early / too late)
  - out-of-window weekend
  - non-default weekday config (e.g., Saturday enabled)
  - timezone conversion (naive now treated as UTC, converted to local)
  - fail-closed on unparseable timezone
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase

from campaigns.models import Campaign, Organization, Product
from campaigns.services.reply_window import is_within_reply_window


class ReplyWindowTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Test Org', slug='test-org')
        cls.product = Product.objects.create(
            organization=cls.org, name='Test Product', slug='test-product',
        )
        # Default campaign uses migration 0019 defaults:
        # 9-18 Mon-Fri Europe/Dublin, 5-min grace
        cls.campaign = Campaign.objects.create(
            name='Reply Window Test',
            product='other',
            product_ref=cls.product,
            from_email='test@example.test',
            from_name='Test',
        )

    def _dublin(self, iso: str) -> datetime:
        """Build a Europe/Dublin-aware datetime from a naive ISO string."""
        return datetime.fromisoformat(iso).replace(tzinfo=ZoneInfo('Europe/Dublin'))

    def test_weekday_midday_inside_window(self):
        now = self._dublin('2026-04-15T12:00:00')
        self.assertTrue(is_within_reply_window(self.campaign, now))

    def test_weekday_early_morning_outside_window(self):
        now = self._dublin('2026-04-15T06:30:00')
        self.assertFalse(is_within_reply_window(self.campaign, now))

    def test_weekday_late_evening_outside_window(self):
        now = self._dublin('2026-04-15T19:00:00')
        self.assertFalse(is_within_reply_window(self.campaign, now))

    def test_weekday_boundary_inclusive_start(self):
        now = self._dublin('2026-04-15T09:00:00')
        self.assertTrue(is_within_reply_window(self.campaign, now))

    def test_weekday_boundary_exclusive_end(self):
        now = self._dublin('2026-04-15T18:00:00')
        self.assertFalse(is_within_reply_window(self.campaign, now))

    def test_saturday_outside_default_weekdays(self):
        now = self._dublin('2026-04-18T12:00:00')
        self.assertFalse(is_within_reply_window(self.campaign, now))

    def test_sunday_outside_default_weekdays(self):
        now = self._dublin('2026-04-19T12:00:00')
        self.assertFalse(is_within_reply_window(self.campaign, now))

    def test_saturday_enabled_via_custom_weekdays(self):
        self.campaign.reply_window_days = '0,1,2,3,4,5'
        self.campaign.save(update_fields=['reply_window_days', 'updated_at'])
        now = self._dublin('2026-04-18T12:00:00')
        self.assertTrue(is_within_reply_window(self.campaign, now))

    def test_naive_utc_is_converted_to_local(self):
        """naive datetime treated as UTC; 09:30 UTC = 10:30 IST (within 9-18)."""
        naive_utc = datetime(2026, 4, 15, 9, 30)
        self.assertTrue(is_within_reply_window(self.campaign, naive_utc))

    def test_fail_closed_on_bad_timezone(self):
        self.campaign.reply_window_timezone = 'Mars/Olympus_Mons'
        self.campaign.save(update_fields=['reply_window_timezone', 'updated_at'])
        now = self._dublin('2026-04-15T12:00:00')
        self.assertFalse(is_within_reply_window(self.campaign, now))

    def test_none_campaign_returns_false(self):
        self.assertFalse(is_within_reply_window(None))
