"""
Email Service for Paperclip Outreach
Handles email sending with AWS SES SMTP integration
"""
import logging
import uuid
import smtplib
from typing import List, Optional, Dict, Any
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr
from django.conf import settings

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def send_email(
        to_emails: List[str],
        subject: str,
        body_html: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
        cc_emails: Optional[List[str]] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> Dict[str, str]:
        from_address = from_email or getattr(settings, 'AWS_SES_FROM_EMAIL', 'noreply@example.com')
        mode = getattr(settings, 'EMAIL_SERVICE_MODE', 'console')

        if from_name:
            from_header = formataddr((from_name, from_address))
        else:
            from_header = from_address

        logger.info("=" * 80)
        logger.info(f"[EMAIL SERVICE - {mode.upper()}]")
        logger.info(f"From: {from_header}")
        logger.info(f"To: {', '.join(to_emails)}")
        if cc_emails:
            logger.info(f"CC: {', '.join(cc_emails)}")
        if reply_to:
            logger.info(f"Reply-To: {reply_to}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Body Length: {len(body_html)} characters")
        if attachments:
            logger.info(f"Attachments: {len(attachments)} file(s)")
            for attachment in attachments:
                logger.info(f"  - {attachment.get('filename', 'unknown')} ({attachment.get('content_type', 'unknown')})")
        logger.info("=" * 80)

        if mode == 'ses':
            try:
                smtp_host = f"email-smtp.{settings.AWS_REGION}.amazonaws.com"
                smtp_port = 587
                smtp_username = settings.AWS_SMTP_USERNAME
                smtp_password = settings.AWS_SMTP_PASSWORD

                msg = MIMEMultipart('mixed')
                msg['Subject'] = subject
                msg['From'] = from_header
                msg['To'] = ', '.join(to_emails)

                if cc_emails:
                    msg['Cc'] = ', '.join(cc_emails)

                if reply_to:
                    msg['Reply-To'] = reply_to

                full_html = EmailService._wrap_html(body_html)

                msg_body = MIMEMultipart('alternative')
                html_part = MIMEText(full_html, 'html')
                msg_body.attach(html_part)
                msg.attach(msg_body)

                if attachments:
                    for attachment in attachments:
                        att = MIMEApplication(attachment['content'])
                        att.add_header('Content-Disposition', 'attachment', filename=attachment['filename'])
                        msg.attach(att)

                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_username, smtp_password)
                    all_recipients = to_emails + (cc_emails or [])
                    server.sendmail(from_address, all_recipients, msg.as_string())

                message_id = f"smtp-{uuid.uuid4()}"
                logger.info(f"Email sent successfully via AWS SES SMTP. MessageId: {message_id}")
                return {"status": "sent", "message_id": message_id}

            except Exception as e:
                logger.error(f"SMTP Error: {str(e)}")
                raise Exception(f"Failed to send email: {str(e)}")
        else:
            return {"status": "queued", "message_id": f"console-{uuid.uuid4()}"}

    @staticmethod
    def send_reply(
        to_email: str,
        subject: str,
        body_html: str,
        in_reply_to: str,
        references: str = '',
        from_email: str = None,
        from_name: str = None,
    ) -> Dict[str, str]:
        """Send reply via Zoho SMTP for proper email threading."""
        from_address = from_email or settings.ZOHO_SMTP_EMAIL
        mode = getattr(settings, 'EMAIL_SERVICE_MODE', 'console')

        if from_name:
            from_header = formataddr((from_name, from_address))
        else:
            from_header = from_address

        logger.info("=" * 80)
        logger.info(f"[ZOHO SMTP REPLY - {mode.upper()}]")
        logger.info(f"From: {from_header}")
        logger.info(f"To: {to_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"In-Reply-To: {in_reply_to}")
        logger.info(f"Body Length: {len(body_html)} characters")
        logger.info("=" * 80)

        if mode == 'console':
            msg_id = f"console-reply-{uuid.uuid4()}"
            logger.info(f"[CONSOLE MODE] Would send reply via Zoho SMTP. MessageId: {msg_id}")
            return {"status": "sent", "message_id": msg_id}

        try:
            smtp_host = settings.ZOHO_SMTP_HOST
            smtp_port = settings.ZOHO_SMTP_PORT
            smtp_user = settings.ZOHO_SMTP_EMAIL
            smtp_pass = settings.ZOHO_SMTP_PASSWORD

            msg = MIMEMultipart('mixed')
            msg['Subject'] = subject
            msg['From'] = from_header
            msg['To'] = to_email

            if in_reply_to:
                msg['In-Reply-To'] = in_reply_to
                msg['References'] = references or in_reply_to

            full_html = EmailService._wrap_html(body_html)
            msg_body = MIMEMultipart('alternative')
            html_part = MIMEText(full_html, 'html')
            msg_body.attach(html_part)
            msg.attach(msg_body)

            # Port 465 = direct SSL, port 587 = STARTTLS
            if smtp_port == 465:
                with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(from_address, [to_email], msg.as_string())
            else:
                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(from_address, [to_email], msg.as_string())

            message_id = f"zoho-reply-{uuid.uuid4()}"
            logger.info(f"Reply sent via Zoho SMTP. MessageId: {message_id}")
            return {"status": "sent", "message_id": message_id}

        except Exception as e:
            logger.error(f"Zoho SMTP Error: {str(e)}")
            raise Exception(f"Failed to send reply via Zoho: {str(e)}")

    @staticmethod
    def _wrap_html(body_html: str) -> str:
        if body_html.strip().lower().startswith('<!doctype') or body_html.strip().lower().startswith('<html'):
            return body_html

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333333;">
{body_html}
</body>
</html>"""

    @staticmethod
    def render_template(template_content: str, variables: Dict[str, str]) -> str:
        import re
        rendered = template_content
        for key, value in variables.items():
            pattern = r'\{\{' + ''.join(
                f'(?:<[^>]*>)?{re.escape(char)}(?:</[^>]*>)?' for char in key
            ) + r'\}\}'
            rendered = re.sub(pattern, str(value or ''), rendered)
        return rendered
