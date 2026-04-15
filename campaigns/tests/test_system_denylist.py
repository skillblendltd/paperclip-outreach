"""G4 — unit tests for is_system_email() sender + subject denylist.

This is the safety net that prevented the 27-bad-sends incident from
happening again. On 2026-04-15 the AI reply pipeline sent replies to:
  - DocuSign notification address (dse@eumail.docusign.net)
  - Prakash's own calendar invite (Accepted: Appointment booked:)
  - Auto-ack messages ([Request received])
  - Out-of-office auto-replies

The fix (G4) added a sender + subject denylist at the top of the
classification path. This test suite is the regression guard — any
future edit that removes a denylist entry, breaks case-insensitivity,
or fails on an edge-case subject prefix will fail at least one of
these tests.

**Test behavior, not implementation.** These tests call
`is_system_email(from_email, subject)` directly and assert the
boolean return. They do not touch IMAP, DB, or Django models. This
is the simplest possible regression check for a critical safety
filter.
"""
from django.test import SimpleTestCase

from campaigns.management.commands.check_replies import is_system_email


class SystemEmailDenylistTests(SimpleTestCase):
    """Every entry in SYSTEM_SENDER_DENYLIST_SUBSTRINGS and
    SYSTEM_SUBJECT_DENYLIST_PREFIXES must produce True.

    Case sensitivity: both sender and subject matching must be
    case-insensitive. Email addresses mix case frequently (DSE@, Dse@,
    dse@) and subject prefixes arrive from dozens of mail clients
    that capitalize differently ("Auto-Reply:" vs "AUTO-REPLY:").
    """

    # ------------------------------------------------------------------
    # Sender denylist — lowercase inputs
    # ------------------------------------------------------------------

    def test_postmaster_sender_blocked(self):
        self.assertTrue(is_system_email('postmaster@example.com', 'Delivery failure'))

    def test_mailer_daemon_sender_blocked(self):
        self.assertTrue(is_system_email('mailer-daemon@mx.google.com', 'Undelivered'))

    def test_noreply_sender_blocked(self):
        self.assertTrue(is_system_email('noreply@company.com', 'Account update'))

    def test_no_reply_sender_blocked(self):
        self.assertTrue(is_system_email('no-reply@notifications.com', 'Alert'))

    def test_do_not_reply_sender_blocked(self):
        self.assertTrue(is_system_email('do-not-reply@corp.com', 'Newsletter'))

    def test_bounces_sender_blocked(self):
        self.assertTrue(is_system_email('bounces@list.example.com', 'Return'))

    def test_docusign_dse_sender_blocked(self):
        self.assertTrue(is_system_email('dse@eumail.docusign.net', 'Signing request'))

    def test_docusign_domain_blocked_regardless_of_local_part(self):
        self.assertTrue(is_system_email('whatever@docusign.net', 'Please sign'))

    def test_calendar_notification_sender_blocked(self):
        self.assertTrue(
            is_system_email('calendar-notification@google.com', 'Meeting'))

    def test_github_notifications_blocked(self):
        self.assertTrue(
            is_system_email('notifications@github.com', 'Pull request opened'))

    # ------------------------------------------------------------------
    # Sender denylist — CASE INSENSITIVITY
    # ------------------------------------------------------------------

    def test_sender_denylist_case_insensitive_all_caps(self):
        self.assertTrue(is_system_email('POSTMASTER@EXAMPLE.COM', 'whatever'))

    def test_sender_denylist_case_insensitive_mixed(self):
        self.assertTrue(is_system_email('NoReply@Example.Com', 'whatever'))

    def test_sender_denylist_case_insensitive_docusign(self):
        self.assertTrue(is_system_email('DSE@Eumail.DocuSign.Net', 'anything'))

    # ------------------------------------------------------------------
    # Subject prefix denylist
    # ------------------------------------------------------------------

    def test_auto_reply_subject_blocked(self):
        self.assertTrue(is_system_email('anyone@example.com', 'Auto-reply: on leave'))

    def test_automatic_reply_subject_blocked(self):
        self.assertTrue(
            is_system_email('anyone@example.com', 'Automatic reply: away until Monday'))

    def test_out_of_office_subject_blocked(self):
        self.assertTrue(
            is_system_email('anyone@example.com', 'Out of office: back next week'))

    def test_request_received_subject_blocked(self):
        self.assertTrue(
            is_system_email('sales@company.com', '[Request received] - ref 12345'))

    def test_accepted_calendar_subject_blocked(self):
        self.assertTrue(
            is_system_email('prospect@example.com', 'Accepted: Demo @ 3pm'))

    def test_declined_calendar_subject_blocked(self):
        self.assertTrue(
            is_system_email('prospect@example.com', 'Declined: Demo @ 3pm'))

    def test_tentative_calendar_subject_blocked(self):
        self.assertTrue(
            is_system_email('prospect@example.com', 'Tentative: Demo @ 3pm'))

    def test_docusign_subject_prefix_blocked(self):
        self.assertTrue(
            is_system_email('sender@company.com', 'Document for eSignature'))

    def test_please_docusign_subject_blocked(self):
        self.assertTrue(
            is_system_email('sender@company.com', 'Please DocuSign: Agreement'))

    def test_appointment_booked_subject_blocked(self):
        self.assertTrue(
            is_system_email('calendar@company.com', 'Appointment booked: 3pm Tuesday'))

    def test_undeliverable_subject_blocked(self):
        self.assertTrue(
            is_system_email('anyone@example.com', 'Undeliverable: your message'))

    def test_delivery_status_notification_subject_blocked(self):
        self.assertTrue(
            is_system_email('anyone@example.com', 'Delivery Status Notification (Failure)'))

    # ------------------------------------------------------------------
    # Subject denylist — CASE INSENSITIVITY
    # ------------------------------------------------------------------

    def test_subject_denylist_case_insensitive_all_caps(self):
        self.assertTrue(
            is_system_email('anyone@example.com', 'AUTO-REPLY: OUT OF OFFICE'))

    def test_subject_denylist_case_insensitive_title_case(self):
        self.assertTrue(
            is_system_email('anyone@example.com', 'Accepted: Quick Chat'))

    def test_subject_denylist_whitespace_stripped(self):
        """Leading whitespace on the subject must not fool the prefix match.
        Some mail clients indent quoted subjects.
        """
        self.assertTrue(
            is_system_email('anyone@example.com', '   Auto-reply: stuff'))

    # ------------------------------------------------------------------
    # Negative cases — real prospect replies must NOT be blocked
    # ------------------------------------------------------------------

    def test_normal_prospect_email_not_blocked(self):
        self.assertFalse(
            is_system_email('john@acmeshop.com', 'Re: your intro email'))

    def test_gmail_prospect_not_blocked(self):
        self.assertFalse(
            is_system_email('sarah.jones@gmail.com', 'Re: quick question about your crew'))

    def test_interested_reply_not_blocked(self):
        self.assertFalse(
            is_system_email('ceo@startup.ie', 'Re: interested in a demo'))

    def test_reply_containing_accepted_word_not_blocked(self):
        """The word 'accepted' elsewhere in the subject must not trip the
        prefix match. Only the EXACT prefix 'Accepted:' should block.
        """
        self.assertFalse(
            is_system_email('prospect@example.com',
                            'Re: I accepted your offer and want to proceed'))

    def test_reply_containing_docusign_word_not_blocked(self):
        self.assertFalse(
            is_system_email('prospect@example.com',
                            'Re: do you integrate with DocuSign?'))

    def test_reply_from_noreply_lookalike_not_blocked(self):
        """A prospect who happens to have 'reply' in their address but
        is not on the denylist substrings should not be blocked.
        """
        self.assertFalse(
            is_system_email('replysoon@prospect.com', 'Re: quick question'))

    def test_empty_inputs_returns_false(self):
        """Defensive: empty from/subject must not crash or block."""
        self.assertFalse(is_system_email('', ''))

    def test_none_safe(self):
        """Defensive: None inputs must not crash."""
        self.assertFalse(is_system_email(None, None))
