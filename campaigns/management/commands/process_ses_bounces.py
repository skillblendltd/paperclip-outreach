"""
Poll the SQS bounce queue and process SES bounce / complaint / reject events.

Architecture:
    SES sending (with Configuration Set 'paperclip-bounces')
        -> SNS topic 'taggiq-ses-bounces'
            -> SQS queue 'taggiq-ses-bounces-queue'
                -> this command (cron every 15 min)
                    -> Suppression created + Prospect.send_enabled=False

Bounce type discrimination (CTO requirement):
    - Permanent → suppress (hard bounce)
    - Transient → log only, do NOT suppress (soft bounce — mailbox full / temp / OOO)
    - Complaint → suppress with reason='complaint'
    - Reject → suppress with reason='bounce' (SES rejected before sending)

Idempotent: Suppression.objects.get_or_create() prevents duplicates.
Fail-closed: AWS errors logged, command continues — next cron tick retries.
"""
import json
import logging
import os
from datetime import datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.core.management.base import BaseCommand
from django.conf import settings

from campaigns.models import Suppression, Prospect, Product, EmailLog


logger = logging.getLogger(__name__)


SQS_QUEUE_URL_SETTING = 'AWS_SES_BOUNCES_SQS_URL'
SQS_REGION_SETTING = 'AWS_REGION'
DEFAULT_REGION = 'eu-west-1'

# Per-poll batch (SQS max is 10)
RECEIVE_BATCH_SIZE = 10
RECEIVE_WAIT_SECONDS = 5  # short long-poll
VISIBILITY_TIMEOUT_SECONDS = 60


class Command(BaseCommand):
    help = 'Poll SQS for SES bounce/complaint events and create Suppression rows.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-batches',
            type=int,
            default=20,
            help='Max number of SQS receive batches per run (each batch is up to 10 messages). Default 20.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Parse and log messages, but do NOT create Suppressions or delete from queue.',
        )

    def handle(self, *args, **options):
        max_batches = options['max_batches']
        dry_run = options['dry_run']

        queue_url = getattr(settings, SQS_QUEUE_URL_SETTING, '') or os.environ.get(SQS_QUEUE_URL_SETTING, '')
        region = getattr(settings, SQS_REGION_SETTING, '') or os.environ.get(SQS_REGION_SETTING, DEFAULT_REGION)

        if not queue_url:
            logger.error('Missing %s setting/env. Cannot poll SQS.', SQS_QUEUE_URL_SETTING)
            self.stdout.write(self.style.ERROR(f'Missing {SQS_QUEUE_URL_SETTING}'))
            return

        try:
            sqs = boto3.client('sqs', region_name=region)
        except (BotoCoreError, ClientError) as exc:
            logger.error('Failed to create SQS client: %s', exc)
            return

        stats = {
            'messages_received': 0,
            'permanent_bounces': 0,
            'transient_bounces': 0,
            'complaints': 0,
            'rejects': 0,
            'unrecognised': 0,
            'errors': 0,
            'suppressions_created': 0,
            'prospects_disabled': 0,
        }

        for batch_idx in range(max_batches):
            try:
                resp = sqs.receive_message(
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=RECEIVE_BATCH_SIZE,
                    WaitTimeSeconds=RECEIVE_WAIT_SECONDS,
                    VisibilityTimeout=VISIBILITY_TIMEOUT_SECONDS,
                )
            except (BotoCoreError, ClientError) as exc:
                logger.error('SQS receive_message failed (batch %d): %s', batch_idx, exc)
                stats['errors'] += 1
                break  # don't hammer if SQS is angry

            messages = resp.get('Messages', [])
            if not messages:
                logger.info('No messages in batch %d, queue drained.', batch_idx)
                break

            for msg in messages:
                stats['messages_received'] += 1
                receipt_handle = msg['ReceiptHandle']
                try:
                    self._process_message(msg, stats, dry_run=dry_run)
                except Exception:
                    logger.exception('Unhandled error processing SQS message; leaving in queue')
                    stats['errors'] += 1
                    continue  # do NOT delete on error — let SQS retry

                if not dry_run:
                    try:
                        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
                    except (BotoCoreError, ClientError) as exc:
                        logger.error('Failed to delete SQS message: %s', exc)
                        stats['errors'] += 1

        # Summary
        self.stdout.write(self.style.SUCCESS(
            f'Processed: messages={stats["messages_received"]} '
            f'perm-bounces={stats["permanent_bounces"]} '
            f'transient-bounces={stats["transient_bounces"]} '
            f'complaints={stats["complaints"]} '
            f'rejects={stats["rejects"]} '
            f'suppressions+={stats["suppressions_created"]} '
            f'prospects-disabled={stats["prospects_disabled"]} '
            f'errors={stats["errors"]}'
        ))
        logger.info('process_ses_bounces summary: %s', stats)

    # ------------------------------------------------------------------
    # Per-message processing
    # ------------------------------------------------------------------
    def _process_message(self, sqs_msg, stats, dry_run=False):
        """Parse the SNS-wrapped SES notification and act on it.

        SQS body is a stringified SNS notification. SNS notification has 'Message'
        field which is itself a stringified SES event JSON.
        """
        body = sqs_msg.get('Body', '')
        try:
            sns_envelope = json.loads(body)
        except json.JSONDecodeError:
            logger.error('SQS message body not JSON: %s', body[:300])
            stats['unrecognised'] += 1
            return

        # Some envelope types have the SES JSON nested inside Message, others (raw delivery)
        # have it directly at the top level. Handle both.
        ses_json = None
        if 'Message' in sns_envelope and isinstance(sns_envelope['Message'], str):
            try:
                ses_json = json.loads(sns_envelope['Message'])
            except json.JSONDecodeError:
                logger.error('SNS Message not JSON: %s', sns_envelope['Message'][:300])
                stats['unrecognised'] += 1
                return
        else:
            ses_json = sns_envelope

        notification_type = (
            ses_json.get('notificationType')
            or ses_json.get('eventType')
            or ''
        )

        if notification_type == 'Bounce':
            self._handle_bounce(ses_json, stats, dry_run=dry_run)
        elif notification_type == 'Complaint':
            self._handle_complaint(ses_json, stats, dry_run=dry_run)
        elif notification_type == 'Reject':
            self._handle_reject(ses_json, stats, dry_run=dry_run)
        elif notification_type in ('Delivery', 'Send', 'Open', 'Click'):
            # Should not be in this queue (config set scope is Bounce/Complaint/Reject)
            # If they leak through, ignore silently.
            logger.debug('Ignoring %s event (not in scope)', notification_type)
        else:
            logger.warning('Unrecognised notification type: %s', notification_type)
            stats['unrecognised'] += 1

    # ------------------------------------------------------------------
    def _handle_bounce(self, ses_json, stats, dry_run=False):
        bounce = ses_json.get('bounce', {})
        bounce_type = bounce.get('bounceType', 'Unknown')
        bounce_subtype = bounce.get('bounceSubType', 'Unknown')
        timestamp = bounce.get('timestamp', '')
        recipients = bounce.get('bouncedRecipients', [])
        ses_message_id = ses_json.get('mail', {}).get('messageId', '')
        sending_domain = self._extract_domain(ses_json.get('mail', {}).get('source', ''))

        if bounce_type == 'Transient':
            stats['transient_bounces'] += 1
            for r in recipients:
                addr = r.get('emailAddress', '').lower()
                logger.info(
                    'Transient bounce (NOT suppressed): %s subType=%s domain=%s ses_msg=%s',
                    addr, bounce_subtype, sending_domain, ses_message_id
                )
            return  # CTO rule: do NOT suppress transient bounces

        if bounce_type == 'Permanent':
            stats['permanent_bounces'] += 1
            for r in recipients:
                addr = r.get('emailAddress', '').lower().strip()
                if not addr:
                    continue
                note = (
                    f'SES Permanent bounce (subType={bounce_subtype}, '
                    f'sending_domain={sending_domain}, ses_message_id={ses_message_id}, '
                    f'timestamp={timestamp})'
                )
                if not dry_run:
                    self._suppress(addr, reason='bounce', notes=note, stats=stats)
                logger.info('Permanent bounce suppressed: %s subType=%s', addr, bounce_subtype)
            return

        # Bounce type other than Permanent/Transient (rare — Undetermined)
        logger.warning('Bounce with unrecognised type %s — treating as Transient (no suppression)', bounce_type)
        stats['transient_bounces'] += 1

    # ------------------------------------------------------------------
    def _handle_complaint(self, ses_json, stats, dry_run=False):
        stats['complaints'] += 1
        complaint = ses_json.get('complaint', {})
        timestamp = complaint.get('timestamp', '')
        feedback_type = complaint.get('complaintFeedbackType', 'unspecified')
        recipients = complaint.get('complainedRecipients', [])
        ses_message_id = ses_json.get('mail', {}).get('messageId', '')
        sending_domain = self._extract_domain(ses_json.get('mail', {}).get('source', ''))

        for r in recipients:
            addr = r.get('emailAddress', '').lower().strip()
            if not addr:
                continue
            note = (
                f'SES Complaint (feedback={feedback_type}, '
                f'sending_domain={sending_domain}, ses_message_id={ses_message_id}, '
                f'timestamp={timestamp})'
            )
            if not dry_run:
                self._suppress(addr, reason='complaint', notes=note, stats=stats)
            logger.warning('Complaint suppressed: %s feedback=%s', addr, feedback_type)

    # ------------------------------------------------------------------
    def _handle_reject(self, ses_json, stats, dry_run=False):
        stats['rejects'] += 1
        # Reject events have different shape — recipient is in mail.destination
        mail = ses_json.get('mail', {})
        recipients = mail.get('destination', [])
        reason = ses_json.get('reject', {}).get('reason', 'unknown')
        ses_message_id = mail.get('messageId', '')
        sending_domain = self._extract_domain(mail.get('source', ''))

        for addr in recipients:
            addr = (addr or '').lower().strip()
            if not addr:
                continue
            note = (
                f'SES Reject (reason={reason}, '
                f'sending_domain={sending_domain}, ses_message_id={ses_message_id})'
            )
            if not dry_run:
                self._suppress(addr, reason='bounce', notes=note, stats=stats)
            logger.warning('Reject suppressed: %s reason=%s', addr, reason)

    # ------------------------------------------------------------------
    def _suppress(self, email, reason, notes, stats):
        """Create Suppression rows (one per product the address has been emailed from)
        and disable matching Prospect rows across all campaigns.
        """
        # Find products this address has been targeted in
        product_ids = set(Prospect.objects.filter(
            email__iexact=email
        ).values_list('campaign__product_ref', flat=True).distinct())
        product_ids.discard(None)

        if not product_ids:
            # No matching prospect — global suppression
            sup, created = Suppression.objects.get_or_create(
                email=email, product=None,
                defaults={'reason': reason, 'notes': notes},
            )
            if created:
                stats['suppressions_created'] += 1
        else:
            for pid in product_ids:
                product = Product.objects.filter(id=pid).first()
                if not product:
                    continue
                sup, created = Suppression.objects.get_or_create(
                    email=email, product=product,
                    defaults={'reason': reason, 'notes': notes},
                )
                if created:
                    stats['suppressions_created'] += 1

        # Disable across all campaigns (idempotent)
        n = Prospect.objects.filter(
            email__iexact=email, send_enabled=True
        ).update(send_enabled=False)
        if n:
            stats['prospects_disabled'] += n

    # ------------------------------------------------------------------
    def _extract_domain(self, source_email):
        """Extract the sending domain from 'Prakash <prakash@mail.taggiq.com>' etc."""
        if not source_email:
            return ''
        if '<' in source_email and '>' in source_email:
            source_email = source_email.split('<', 1)[1].rsplit('>', 1)[0]
        if '@' in source_email:
            return source_email.split('@', 1)[1].strip().lower()
        return source_email.strip().lower()
