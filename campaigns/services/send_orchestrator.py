"""
Core send-one-email function.
Consolidated from views.py outreach_send and process_queue.py send logic.
"""
import logging

from django.utils import timezone

from campaigns.models import EmailLog
from campaigns.email_service import EmailService
from campaigns.services.template_resolver import render, determine_variant

logger = logging.getLogger(__name__)


def send_one(campaign, prospect, template, sequence_number, dry_run=False):
    """
    Render template, send via EmailService, log to EmailLog, update prospect.
    Returns dict: {status, log_id, error, subject}
    """
    subject, body_html = render(template, prospect, campaign)
    ab_variant = determine_variant(prospect)

    if dry_run:
        return {
            'status': 'dry_run',
            'log_id': None,
            'error': None,
            'subject': subject,
            'prospect': prospect.business_name,
            'email': prospect.email,
            'sequence': sequence_number,
            'variant': ab_variant,
        }

    # Send
    try:
        result = EmailService.send_email(
            to_emails=[prospect.email],
            subject=subject,
            body_html=body_html,
            from_name=campaign.from_name or None,
            from_email=campaign.from_email or None,
            reply_to=campaign.reply_to_email or None,
        )
        status = 'sent'
        error_msg = ''
        ses_id = result.get('message_id', '')
    except Exception as e:
        status = 'failed'
        error_msg = str(e)
        ses_id = ''
        logger.exception(f'Failed to send to {prospect.email}')

    # Log
    log = EmailLog.objects.create(
        campaign=campaign,
        prospect=prospect,
        to_email=prospect.email,
        subject=subject,
        body_html=body_html,
        sequence_number=sequence_number,
        template_name=template.template_name,
        ab_variant=ab_variant,
        status=status,
        ses_message_id=ses_id,
        error_message=error_msg,
        triggered_by='send_sequences',
    )

    # Update prospect
    if status == 'sent':
        prospect.emails_sent += 1
        prospect.last_emailed_at = timezone.now()
        if prospect.status == 'new':
            prospect.status = 'contacted'
        prospect.save(update_fields=['emails_sent', 'last_emailed_at', 'status', 'updated_at'])

    return {
        'status': status,
        'log_id': str(log.id),
        'error': error_msg or None,
        'subject': subject,
        'prospect': prospect.business_name,
        'email': prospect.email,
        'sequence': sequence_number,
        'variant': ab_variant,
    }
