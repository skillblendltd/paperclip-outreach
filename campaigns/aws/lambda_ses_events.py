"""
AWS Lambda function to handle SES bounce and complaint events.

Triggered by SNS topic (paperclip-outreach-ses-events) which is subscribed
to SES Configuration Set event notifications.

This Lambda suppresses email addresses based on bounce and complaint feedback
to protect sender reputation and prevent repeated sends to bad addresses.

Environment variables:
  - DB_HOST: PostgreSQL host
  - DB_NAME: Database name
  - DB_USER: Database user
  - DB_PASSWORD: Database password
  - DB_PORT: Database port (default 5432)
"""
import json
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Main handler - processes SNS message containing SES event.
    SNS wraps the actual SES event in Records[0].Sns.Message (as JSON string).
    """
    try:
        # Parse SNS wrapper
        sns_message = event['Records'][0]['Sns']['Message']
        ses_event = json.loads(sns_message)

        event_type = ses_event.get('eventType')
        logger.info(f'Processing SES event type: {event_type}')

        if event_type == 'Bounce':
            handle_bounce(ses_event)
        elif event_type == 'Complaint':
            handle_complaint(ses_event)
        else:
            logger.info(f'Ignoring event type: {event_type}')

        return {'statusCode': 200, 'body': json.dumps('OK')}

    except Exception as e:
        logger.exception(f'Error processing SES event: {e}')
        return {'statusCode': 500, 'body': json.dumps(f'Error: {str(e)}')}


def handle_bounce(event):
    """
    Process SES Bounce event.

    Permanent bounces (hard bounces): suppress immediately.
    Transient bounces (soft bounces): increment counter, suppress after 3 attempts.
    """
    bounce_data = event.get('bounce', {})
    bounce_type = bounce_data.get('bounceType', 'Undetermined')  # Permanent, Transient, Undetermined
    bounce_subtype = bounce_data.get('bounceSubType', '')  # General, MailFromDomainNotVerified, etc.
    timestamp = event.get('mail', {}).get('timestamp', datetime.utcnow().isoformat())

    bounced_recipients = bounce_data.get('bouncedRecipients', [])

    logger.info(f'Processing {bounce_type} bounce with {len(bounced_recipients)} recipients')

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for recipient in bounced_recipients:
                email = recipient.get('emailAddress', '').lower()
                status = recipient.get('status', '')
                diagnostic = recipient.get('diagnosticCode', '')

                if not email:
                    continue

                if bounce_type == 'Permanent':
                    suppress_email(cur, email, 'hard_bounce', f'{bounce_subtype} - {diagnostic}')
                elif bounce_type == 'Transient':
                    increment_soft_bounce(cur, email, f'{bounce_subtype} - {diagnostic}')
                else:
                    logger.warning(f'Undetermined bounce for {email}: {diagnostic}')

        conn.commit()


def handle_complaint(event):
    """
    Process SES Complaint event.
    User marked email as spam/complaint - suppress immediately and permanently.
    """
    complaint_data = event.get('complaint', {})
    complained_recipients = complaint_data.get('complainedRecipients', [])
    complaint_feedback_type = complaint_data.get('complaintFeedbackType', 'other')

    logger.info(f'Processing complaint with {len(complained_recipients)} recipients')

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for recipient in complained_recipients:
                email = recipient.get('emailAddress', '').lower()

                if not email:
                    continue

                suppress_email(cur, email, 'complained', f'Feedback type: {complaint_feedback_type}')

        conn.commit()


def suppress_email(cur, email, reason, notes=''):
    """
    Add email to global suppression list (across ALL products).

    Bounces and complaints are universal signals - a bounced or complained address
    should never receive ANY email from ANY product.

    Uses ON CONFLICT to upsert: if address already suppressed for another reason,
    update the reason to the new feedback.
    """
    try:
        logger.info(f'Suppressing email: {email} (reason: {reason})')

        # Global suppression: product_id = NULL
        cur.execute('''
            INSERT INTO suppressions (id, email, product_id, reason, notes, created_at, updated_at)
            VALUES (gen_random_uuid(), %s, NULL, %s, %s, NOW(), NOW())
            ON CONFLICT (email, product_id) DO UPDATE SET
                reason = EXCLUDED.reason,
                notes = EXCLUDED.notes,
                updated_at = NOW()
        ''', (email, reason, notes))

        logger.info(f'Successfully suppressed: {email}')

    except Exception as e:
        logger.exception(f'Error suppressing {email}: {e}')
        raise


def increment_soft_bounce(cur, email, diagnostic=''):
    """
    Increment soft bounce counter for an email.
    When counter reaches 3, suppress permanently.
    """
    try:
        # Check current count
        cur.execute('''
            SELECT soft_bounce_count FROM suppressions
            WHERE email = %s AND product_id IS NULL
        ''', (email,))

        result = cur.fetchone()

        if result:
            # Already suppressed - increment counter
            new_count = result[0] + 1
            cur.execute('''
                UPDATE suppressions
                SET soft_bounce_count = %s, updated_at = NOW()
                WHERE email = %s AND product_id IS NULL
            ''', (new_count, email))

            logger.info(f'Soft bounce counter for {email}: {new_count}')

            if new_count >= 3:
                # Escalate to permanent suppression
                cur.execute('''
                    UPDATE suppressions
                    SET reason = %s, notes = %s, updated_at = NOW()
                    WHERE email = %s AND product_id IS NULL
                ''', ('soft_bounce', f'Reached 3 soft bounces: {diagnostic}', email))
                logger.warning(f'Email {email} suppressed after 3 soft bounces')
        else:
            # New suppression for this email (or concurrent insert - handled by ON CONFLICT)
            cur.execute('''
                INSERT INTO suppressions (id, email, product_id, reason, soft_bounce_count, notes, created_at, updated_at)
                VALUES (gen_random_uuid(), %s, NULL, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (email, product_id) DO UPDATE SET
                    soft_bounce_count = soft_bounce_count + 1,
                    updated_at = NOW()
            ''', (email, 'soft_bounce', 1, diagnostic))

            logger.info(f'Created soft bounce suppression for {email} (count: 1)')

    except Exception as e:
        logger.exception(f'Error incrementing soft bounce for {email}: {e}')
        raise


def get_db_connection():
    """Create and return a PostgreSQL connection using environment variables."""
    import os

    host = os.getenv('DB_HOST', 'localhost')
    db_name = os.getenv('DB_NAME', 'paperclip_outreach')
    user = os.getenv('DB_USER', 'postgres')
    password = os.getenv('DB_PASSWORD', '')
    port = os.getenv('DB_PORT', '5432')

    conn = psycopg2.connect(
        host=host,
        database=db_name,
        user=user,
        password=password,
        port=port
    )

    return conn
