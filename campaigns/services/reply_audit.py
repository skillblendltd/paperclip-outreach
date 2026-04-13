"""
Deterministic detectors for AI-generated email replies.

Pure-regex checks that catch rule violations the prompt is supposed to prevent
but the model might emit anyway. Used by:
  - send_ai_reply (pre-send blocking, distinct exit codes per violation)
  - handle_replies (post-run audit, log warnings)

Org-agnostic: every detector accepts the persona's signature name and length
thresholds as parameters, so the same code serves Lisa, Prakash-TaggIQ,
Prakash-FP, and any future persona without modification.
"""
import re

# ---------- regex patterns (persona-independent) ----------

_PRICE_PATTERNS = [
    # Currency followed by a number (EUR 18, € 25, euros 30, $40, £15)
    re.compile(r'\b(?:eur|euros?|€|gbp|£|usd|\$)\s*\d{1,4}(?:[.,]\d{1,2})?\b', re.IGNORECASE),
    # A number followed by currency (18 EUR, 25€, 30 GBP)
    re.compile(r'\b\d{1,4}(?:[.,]\d{1,2})?\s*(?:eur|euros?|€|gbp|£)\b', re.IGNORECASE),
    # X each / per item / per piece / per unit - direct unit pricing
    re.compile(r'\b\d{1,4}(?:[.,]\d{1,2})?\s*(?:each|per\s*(?:item|piece|unit)|/\s*(?:item|piece|unit))\b', re.IGNORECASE),
    # Numeric range explicitly tied to "each" or currency
    re.compile(r'\b\d{1,4}\s*[-–to]+\s*\d{1,4}\s*(?:eur|euros?|€|gbp|£|each)\b', re.IGNORECASE),
]

_BOUNCE_LOCAL_PARTS = re.compile(
    r'^(mailer-daemon|postmaster|no-?reply|bounce|bounces|delivery|notifications?|do-?not-?reply|abuse)@',
    re.IGNORECASE,
)


# ---------- helpers ----------

def _strip_html(s):
    return re.sub(r'<[^>]+>', ' ', s or '')


def _strip_signature(text, signature_name):
    """Drop everything from the sign-off line onward.

    The sign-off line looks like 'Cheers,\\n<name>' or 'Thanks,\\n<name>' etc.
    We use the persona's first name (or whatever was passed) to anchor the split
    so the same function works for Lisa, Prakash, Emma, etc.
    """
    if not signature_name:
        return text
    # Match the persona's first word only (e.g. 'Prakash Inani' -> 'Prakash')
    first_name = signature_name.strip().split()[0]
    pattern = re.compile(
        r'(?i)\b(?:cheers|thanks|regards|kind regards|best|sincerely|warm regards),?\s*\n+\s*'
        + re.escape(first_name) + r'\b'
    )
    parts = pattern.split(text, maxsplit=1)
    return parts[0] if parts else text


# ---------- detectors ----------

def detect_price_violation(body_html, signature_name=''):
    """Return the first matching price pattern's match text, or None.

    Strips the signature block before scanning so the persona's address/phone
    digits don't false-positive (e.g. Lisa's '01-485-1205' or '20+ items' qty).
    """
    text = _strip_html(body_html)
    body_only = _strip_signature(text, signature_name)
    for pat in _PRICE_PATTERNS:
        m = pat.search(body_only)
        if m:
            return m.group(0)
    return None


def detect_bounce_reply(to_email):
    """True if to_email is a bounce/autoresponder/no-reply address."""
    if not to_email:
        return False
    return bool(_BOUNCE_LOCAL_PARTS.match(to_email))


def detect_length_violation(body_html, signature_name='', warn_words=130, fail_words=180):
    """Count words in the body excluding the signature.

    Returns (word_count, severity) where severity is one of:
      None   - within budget
      'warn' - over warn threshold but under fail threshold
      'fail' - over fail threshold
    """
    text = _strip_html(body_html)
    body_only = _strip_signature(text, signature_name)
    words = [w for w in re.split(r'\s+', body_only.strip()) if w]
    n = len(words)
    if n >= fail_words:
        return n, 'fail'
    if n >= warn_words:
        return n, 'warn'
    return n, None


def run_all_checks(body_html, to_email, signature_name='', warn_words=130, fail_words=180):
    """Run every detector once and return a list of (severity, code, message) tuples.

    severity: 'warn' or 'fail'
    code:     'price' | 'bounce' | 'length'
    message:  human-readable explanation
    """
    findings = []

    price = detect_price_violation(body_html, signature_name)
    if price:
        findings.append(('fail', 'price', f'price quote detected: "{price}"'))

    if detect_bounce_reply(to_email):
        findings.append(('fail', 'bounce', f'reply addressed to bounce/autoresponder: {to_email}'))

    word_count, length_sev = detect_length_violation(
        body_html, signature_name, warn_words, fail_words
    )
    if length_sev == 'fail':
        findings.append(('fail', 'length', f'body is {word_count} words (limit {fail_words})'))
    elif length_sev == 'warn':
        findings.append(('warn', 'length', f'body is {word_count} words (warn at {warn_words}, target <100)'))

    return findings
