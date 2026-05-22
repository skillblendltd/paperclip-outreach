"""
Email validation utilities for import and send workflows.
Prevents bad email addresses (test domains, malformed) from entering the system.
"""
import logging

logger = logging.getLogger(__name__)

# Known test/placeholder domains that should never be sent to
TEST_DOMAINS = {
    'domain.com',
    'example.com',
    'example.org',
    'test.com',
    'email.com',
    'mail.com',
    'myemail.com',
    'youremail.com',
    'example.mail.com',
    'x2.com',
    'test.mail.com',
    'localhost',
}

# Common placeholder local parts
TEST_LOCAL_PARTS = {
    'user',
    'test',
    'admin',
    'noreply',
    'no-reply',
    'debug',
}


def is_likely_test_email(email: str) -> bool:
    """
    Check if email looks like a test/placeholder address.
    Returns True if email is obviously fake.
    """
    if not email or '@' not in email:
        return True

    try:
        local, domain = email.split('@', 1)
        local_lower = local.lower()
        domain_lower = domain.lower()

        # Check domain
        if domain_lower in TEST_DOMAINS:
            return True

        # Check local part
        if local_lower in TEST_LOCAL_PARTS:
            return True

        return False
    except Exception:
        return True


def clean_email(raw_email: str) -> str:
    """
    Extract clean email from raw input, handling formats like:
    - "email@domain.com"
    - "Name <email@domain.com>"
    - "<email@domain.com>"

    Returns None if unparseable or is a test address.
    """
    if not raw_email:
        return None

    raw = raw_email.strip()
    if not raw:
        return None

    # Extract email from "Name <email@domain>" format
    if '<' in raw and '>' in raw:
        try:
            start = raw.index('<') + 1
            end = raw.index('>')
            email = raw[start:end].strip()
        except (ValueError, IndexError):
            # Malformed brackets
            return None
    else:
        email = raw

    email = email.strip().lower()

    # Basic email format check
    if not email or '@' not in email or len(email) < 5:
        return None

    # Reject test addresses
    if is_likely_test_email(email):
        return None

    return email
