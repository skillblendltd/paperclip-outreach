"""
Email template lookup and rendering.
Consolidated from all sender scripts' template dicts + views.py variable rendering.
"""
import re

from campaigns.models import EmailTemplate


def determine_variant(prospect):
    """Deterministic A/B variant from prospect ID. Consistent with views.py."""
    return 'A' if hash(str(prospect.id)) % 2 == 0 else 'B'


def get_template(campaign, sequence_number, prospect):
    """
    Look up EmailTemplate for this campaign/sequence/variant.
    Returns EmailTemplate instance or None.
    """
    variant = determine_variant(prospect)
    template = EmailTemplate.objects.filter(
        campaign=campaign,
        sequence_number=sequence_number,
        ab_variant=variant,
        is_active=True,
    ).first()
    return template


def render(template, prospect, campaign):
    """
    Apply variable substitution to template subject and body.
    Returns (rendered_subject, rendered_body_html).
    """
    # Extract YEAR from notes/pain_signals
    year = _extract_year(prospect)

    variables = {
        'FNAME': prospect.decision_maker_name.split()[0] if prospect.decision_maker_name else 'there',
        'COMPANY': prospect.business_name or '',
        'CITY': prospect.city or '',
        'SEGMENT': prospect.get_segment_display() if prospect.segment else prospect.business_type or '',
        'YEAR': year or 'a while back',
        'CHAPTER': prospect.region or 'BNI',
        'CALENDAR_LINK': 'https://calendar.app.google/yFLeFoyP3XscHsBs8',
    }

    subject = _substitute(template.subject_template, variables)
    body = _substitute(template.body_html_template, variables)

    # Append unsubscribe footer
    body += campaign.unsubscribe_footer_html

    return subject, body


def _substitute(text, variables):
    """Replace {{VAR}} placeholders with values."""
    for key, value in variables.items():
        text = text.replace(f'{{{{{key}}}}}', str(value))
    return text


def _extract_year(prospect):
    """Extract enquiry year from prospect notes/pain_signals."""
    for field_text in [prospect.pain_signals, prospect.notes]:
        if not field_text:
            continue
        if 'Enquired ' in field_text:
            for part in field_text.split('.'):
                part = part.strip()
                if part.startswith('Enquired '):
                    val = part.replace('Enquired ', '').strip()
                    if val.isdigit() and len(val) == 4:
                        return val
        if 'Enquiry year:' in field_text:
            for part in field_text.split('.'):
                if 'Enquiry year:' in part:
                    val = part.split(':')[-1].strip()
                    if val.isdigit() and len(val) == 4:
                        return val
    return ''
