"""
Tests for email validation utility functions.
"""
from django.test import TestCase
from campaigns.utils import clean_email, is_likely_test_email


class EmailValidatorTests(TestCase):
    """Test email validation and cleaning functions."""

    def test_clean_email_valid_formats(self):
        """Test clean_email with valid email formats."""
        # Plain email
        self.assertEqual(clean_email('john@company.com'), 'john@company.com')

        # With name
        self.assertEqual(clean_email('John Doe <john@company.com>'), 'john@company.com')

        # With angle brackets only
        self.assertEqual(clean_email('<john@company.com>'), 'john@company.com')

        # With whitespace
        self.assertEqual(clean_email('  john@company.com  '), 'john@company.com')
        self.assertEqual(clean_email('John < john@company.com >'), 'john@company.com')

    def test_clean_email_invalid_inputs(self):
        """Test clean_email with invalid inputs."""
        # Empty
        self.assertIsNone(clean_email(''))
        self.assertIsNone(clean_email(None))
        self.assertIsNone(clean_email('   '))

        # No @ symbol
        self.assertIsNone(clean_email('johndomain.com'))

        # Too short
        self.assertIsNone(clean_email('a@b'))

        # Malformed brackets
        self.assertIsNone(clean_email('John < john@company.com'))
        self.assertIsNone(clean_email('john@company.com >'))

    def test_clean_email_test_addresses_rejected(self):
        """Test that test addresses are rejected."""
        test_cases = [
            'user@domain.com',
            'test@example.com',
            'admin@example.org',
            'noreply@mail.com',
            'debug@x2.com',
        ]
        for email in test_cases:
            self.assertIsNone(clean_email(email), f'Should reject {email}')

    def test_is_likely_test_email(self):
        """Test is_likely_test_email detection."""
        # Test domains
        self.assertTrue(is_likely_test_email('anything@domain.com'))
        self.assertTrue(is_likely_test_email('anything@example.com'))
        self.assertTrue(is_likely_test_email('anything@test.com'))
        self.assertTrue(is_likely_test_email('anything@mail.com'))

        # Test local parts
        self.assertTrue(is_likely_test_email('user@realcompany.com'))
        self.assertTrue(is_likely_test_email('test@realcompany.com'))
        self.assertTrue(is_likely_test_email('admin@realcompany.com'))
        self.assertTrue(is_likely_test_email('noreply@realcompany.com'))

        # Real emails (should be False)
        self.assertFalse(is_likely_test_email('john@acme.com'))
        self.assertFalse(is_likely_test_email('sarah@company.co.uk'))
        self.assertFalse(is_likely_test_email('sales@shopname.com'))

    def test_clean_email_case_insensitive(self):
        """Test that emails are lowercased."""
        self.assertEqual(clean_email('JOHN@COMPANY.COM'), 'john@company.com')
        self.assertEqual(clean_email('John Doe <JOHN@COMPANY.COM>'), 'john@company.com')

    def test_clean_email_html_entities_not_present(self):
        """Test that HTML-encoded angle brackets are handled."""
        # Our cleaner should extract the real email if it can
        # but won't handle u003c/u003e (HTML entity encoding)
        # because those are corrupted at the source
        self.assertIsNone(clean_email('u003c<john@company.com>'))
