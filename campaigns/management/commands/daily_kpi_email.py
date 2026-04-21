"""
Send daily pipeline KPI email to Prakash.

Runs weekdays at 8am via cron. Summarizes yesterday's activity
with action-oriented sections: DO NOW, WINS, WATCH, NUMBERS, SYSTEM.

Usage:
    python manage.py daily_kpi_email            # send email
    python manage.py daily_kpi_email --dry-run  # print to stdout only
    python manage.py daily_kpi_email --product taggiq  # one product
"""
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from campaigns.services.analytics import build_daily_email_context

logger = logging.getLogger(__name__)

RECIPIENT = 'prakash@taggiq.com'


def _build_plain_text(ctx):
    """Build plain-text email body from context dict."""
    lines = []
    lines.append(f"PIPELINE DAILY - {ctx['date']}")
    lines.append('')

    # DO NOW
    pending = ctx['do_now']['pending_replies']
    demos = ctx['do_now']['upcoming_demos']
    if pending or demos:
        lines.append('DO NOW:')
        for p in pending:
            lines.append(f"  -> Reply pending {p['hours_waiting']}hrs: {p['prospect_name']} ({p['company']})")
        for d in demos:
            lines.append(f"  -> Demo: {d['prospect_name']} ({d['company']})")
        lines.append('')

    # WINS
    wins = ctx['wins']
    if wins['new_statuses'] or wins['auto_reply_count']:
        lines.append('WINS:')
        for w in wins['new_statuses']:
            lines.append(f"  {w['status']}: {w['name']}, {w['company']}")
        if wins['auto_reply_count']:
            resp = f" (avg {wins['avg_response_min']:.0f} min response time)" if wins['avg_response_min'] else ''
            lines.append(f"  AI replied to {wins['auto_reply_count']} inbounds{resp}")
        lines.append('')

    # WATCH
    cooling = ctx['watch']['cooling_leads']
    if cooling:
        lines.append('WATCH:')
        for c in cooling:
            lines.append(f"  {c['prospect_name']} ({c['company']}) - {c['days_since_touch']}d in {c['status']}")
        lines.append('')

    # NUMBERS
    n = ctx['numbers']
    lines.append('NUMBERS:')
    sent_detail = ''
    if n['sent_by_campaign']:
        parts = [f"{c['campaign__name']}: {c['count']}" for c in n['sent_by_campaign'][:5]]
        sent_detail = f" ({', '.join(parts)})"
    lines.append(f"  Sent: {n['sent_yesterday']}{sent_detail} | Replies: {n['replies']} ({n['reply_rate_pct']}%) | Demos: {n['demos']} | AI cost: ${n['ai_cost_usd']:.2f}")
    lines.append(f"  MTD: {n['mtd_sent']} sent | {n['mtd_replies']} replies | {n['mtd_demos']} demos | ${n['mtd_ai_cost_usd']:.2f} AI cost")
    lines.append('')

    # SYSTEM
    sys_health = ctx['system']
    lines.append('SYSTEM:')
    for name, check in sys_health['checks'].items():
        icon = 'OK' if check['status'] == 'ok' else 'WARN' if check['status'] == 'warn' else 'CRITICAL'
        lines.append(f"  {icon} {name}: {check['message']}")
    lines.append('')

    return '\n'.join(lines)


def _build_html(ctx):
    """Build HTML email body from context dict."""
    plain = _build_plain_text(ctx)
    # Convert to simple HTML - preserve structure
    html_body = plain.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    html_body = html_body.replace('\n', '<br>\n')
    html_body = html_body.replace('DO NOW:', '<b>DO NOW:</b>')
    html_body = html_body.replace('WINS:', '<b>WINS:</b>')
    html_body = html_body.replace('WATCH:', '<b>WATCH:</b>')
    html_body = html_body.replace('NUMBERS:', '<b>NUMBERS:</b>')
    html_body = html_body.replace('SYSTEM:', '<b>SYSTEM:</b>')
    html_body = html_body.replace('CRITICAL', '<span style="color:red">CRITICAL</span>')
    html_body = html_body.replace('WARN', '<span style="color:orange">WARN</span>')

    return f"""<html>
<body style="font-family: monospace; font-size: 13px; line-height: 1.6; color: #333; max-width: 700px;">
{html_body}
<hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
<p style="color: #999; font-size: 11px;">Paperclip Outreach - Daily KPI Report</p>
</body>
</html>"""


class Command(BaseCommand):
    help = 'Send daily pipeline KPI email'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Print to stdout, do not send')
        parser.add_argument('--product', type=str, help='Product slug filter (e.g. taggiq)')
        parser.add_argument('--to', type=str, default=RECIPIENT, help='Recipient email')

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        product = options.get('product')
        recipient = options.get('to', RECIPIENT)

        ctx = build_daily_email_context(product_slug=product)

        plain_text = _build_plain_text(ctx)
        html_body = _build_html(ctx)

        n = ctx['numbers']
        subject = (
            f"Pipeline Daily - {ctx['date']}: "
            f"{n['sent_yesterday']} sent, {n['replies']} replies, {n['demos']} demos"
        )

        if dry_run:
            self.stdout.write(f'Subject: {subject}')
            self.stdout.write(f'To: {recipient}')
            self.stdout.write('')
            self.stdout.write(plain_text)
            return

        # Send via SES (same as campaign emails)
        try:
            from campaigns.email_service import EmailService
            result = EmailService.send_email(
                to_emails=[recipient],
                subject=subject,
                body_html=html_body,
                from_email='noreply@mail.taggiq.com',
                from_name='Paperclip Outreach',
            )
            if result.get('success', True):
                self.stdout.write(self.style.SUCCESS(f'KPI email sent to {recipient}'))
            else:
                self.stdout.write(self.style.ERROR(f'Failed: {result.get("error", "unknown")}'))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'Send failed: {exc}'))
            logger.exception('daily_kpi_email send failed')
