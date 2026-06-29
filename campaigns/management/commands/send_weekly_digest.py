"""
Send weekly digest email for a single campaign to its operators.

Tenant isolation contract:
    Every query in this command MUST filter by the campaign passed via
    --campaign-id. Operators only see data from their own campaign.
    No cross-campaign data may appear in the email body.

Usage:
    python manage.py send_weekly_digest \\
        --campaign-id <uuid> \\
        --to prakash@mail.taggiqpos.com,shah.jamal@fullypromoted.co.uk

    python manage.py send_weekly_digest \\
        --campaign-id <uuid> \\
        --to ops@example.com \\
        --dry-run

Adding a new campaign digest:
    1. Find the campaign ID (Campaign.objects.get(name='...').id)
    2. Add a cron line in docker/cron-entrypoint.sh:
       0 17 * * 5 root ... send_weekly_digest --campaign-id <uuid> --to "<emails>"
    3. Reload cron container
"""
import logging
from collections import Counter
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from campaigns.email_service import EmailService
from campaigns.models import Campaign, EmailLog, InboundEmail

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send weekly digest for a single campaign to specified recipients'

    def add_arguments(self, parser):
        parser.add_argument(
            '--campaign-id',
            required=True,
            help='UUID of the campaign to summarize (REQUIRED for tenant isolation)',
        )
        parser.add_argument(
            '--to',
            required=True,
            help='Comma-separated recipient email addresses',
        )
        parser.add_argument(
            '--from-email',
            default='prakash@mail.taggiqpos.com',
            help='Sender email (must be SES-verified)',
        )
        parser.add_argument(
            '--from-name',
            default='Prakash Inani',
            help='Sender display name',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print to stdout instead of sending',
        )

    def handle(self, *args, **opts):
        # Resolve campaign — fail loud if invalid
        try:
            campaign = Campaign.objects.get(id=opts['campaign_id'])
        except Campaign.DoesNotExist:
            raise CommandError(f"Campaign {opts['campaign_id']} not found")

        recipients = [e.strip() for e in opts['to'].split(',') if e.strip()]
        if not recipients:
            raise CommandError('No recipients provided via --to')

        # Build digest context — EVERY query filtered by campaign
        ctx = self._build_context(campaign)
        html = self._render_html(campaign, ctx)
        subject = f'{campaign.name} - Weekly Digest - {timezone.now().strftime("%d %b %Y")}'

        if opts['dry_run']:
            self.stdout.write(f'Subject: {subject}')
            self.stdout.write(f'To: {", ".join(recipients)}')
            self.stdout.write(f'From: {opts["from_name"]} <{opts["from_email"]}>')
            self.stdout.write('---')
            self.stdout.write(html)
            return

        sent = 0
        failed = 0
        for recipient in recipients:
            try:
                EmailService.send_email(
                    to_emails=[recipient],
                    subject=subject,
                    body_html=html,
                    from_email=opts['from_email'],
                    from_name=opts['from_name'],
                )
                sent += 1
                self.stdout.write(self.style.SUCCESS(f'Sent to {recipient}'))
            except Exception as e:
                failed += 1
                self.stdout.write(self.style.ERROR(f'Failed {recipient}: {e}'))

        self.stdout.write(f'\nSummary: {sent} sent, {failed} failed for {campaign.name}')

    def _build_context(self, campaign):
        """Build all digest stats. EVERY query MUST filter by campaign."""
        week_ago = timezone.now() - timedelta(days=7)

        # Sends this week
        sends = EmailLog.objects.filter(
            campaign=campaign, created_at__gte=week_ago, status='sent',
        )
        sends_by_seq = Counter(sends.values_list('sequence_number', flat=True))

        # Replies this week
        replies = InboundEmail.objects.filter(
            campaign=campaign, received_at__gte=week_ago,
        )
        replies_by_class = Counter(replies.values_list('classification', flat=True))

        # Interested prospects this week
        interested = list(
            replies.filter(classification='interested').select_related('prospect')
        )

        # Pipeline state (campaign-scoped)
        pipeline = Counter(
            campaign.prospects.values_list('status', flat=True)
        )

        # All-time reply rate (campaign-scoped)
        total_sent = EmailLog.objects.filter(campaign=campaign, status='sent').count()
        total_replies = InboundEmail.objects.filter(campaign=campaign).count()
        reply_rate = (total_replies / total_sent * 100) if total_sent else 0

        # AI replies sent this week
        ai_replies = EmailLog.objects.filter(
            campaign=campaign, triggered_by='ai_reply', created_at__gte=week_ago,
        ).count()

        return {
            'week_ago': week_ago,
            'sends_count': sends.count(),
            'sends_by_seq': sends_by_seq,
            'replies_count': replies.count(),
            'replies_by_class': replies_by_class,
            'interested': interested,
            'pipeline': pipeline,
            'reply_rate': reply_rate,
            'ai_replies': ai_replies,
        }

    def _render_html(self, campaign, ctx):
        """Render digest HTML. Campaign name appears in body for clarity."""
        interested_html = ''
        if ctx['interested']:
            rows = ''.join(
                f'<tr>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #eee;">'
                f'{r.prospect.decision_maker_name or r.from_email}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #eee;color:#666;">'
                f'{r.subject[:60]}</td>'
                f'</tr>'
                for r in ctx['interested']
            )
            interested_html = (
                f'<h3 style="margin-top:24px;">Interested replies this week</h3>'
                f'<table style="border-collapse:collapse;width:100%;font-size:14px;">'
                f'{rows}</table>'
            )

        sends_breakdown = '<br>'.join(
            f'Seq {s}: {n}' for s, n in sorted(ctx['sends_by_seq'].items())
        ) or 'No sends this week'

        replies_breakdown = '<br>'.join(
            f'{c}: {n}' for c, n in ctx['replies_by_class'].most_common()
        ) or 'No replies this week'

        pipeline_breakdown = '<br>'.join(
            f'{s}: {n}' for s, n in ctx['pipeline'].most_common()
        )

        date_from = ctx['week_ago'].strftime('%d %b')
        date_to = timezone.now().strftime('%d %b %Y')

        return f"""
<html><body style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#222;max-width:640px;line-height:1.55;">

<p>Hi,</p>
<p>Here is your weekly digest for the <b>{campaign.name}</b> campaign.</p>

<h3 style="color:#1a1a1a;">This week ({date_from} - {date_to})</h3>

<table style="border-collapse:collapse;width:100%;margin-top:12px;">
<tr>
<td style="background:#f8f8f8;padding:14px;border:1px solid #ddd;width:50%;">
<b>Sends: {ctx['sends_count']}</b><br>
<span style="color:#666;font-size:13px;">{sends_breakdown}</span>
</td>
<td style="background:#f8f8f8;padding:14px;border:1px solid #ddd;">
<b>Replies: {ctx['replies_count']}</b><br>
<span style="color:#666;font-size:13px;">{replies_breakdown}</span>
</td>
</tr>
<tr>
<td style="padding:14px;border:1px solid #ddd;">
<b>AI auto-replies sent:</b> {ctx['ai_replies']}
</td>
<td style="padding:14px;border:1px solid #ddd;">
<b>All-time reply rate:</b> {ctx['reply_rate']:.1f}%
</td>
</tr>
</table>

{interested_html}

<h3 style="margin-top:24px;">Pipeline state</h3>
<p style="color:#444;line-height:1.8;">{pipeline_breakdown}</p>

<h3 style="margin-top:24px;">Bookings</h3>
<p>Booking tracking is currently manual. If any prospects booked a Calendly slot this week, reply with names and we will mark them as demo_scheduled.</p>

<p>Any flagged conversations needing human input will be listed above. Otherwise the system is running on autopilot.</p>

<p>Cheers,<br>
Prakash<br>
<span style="color:#666;font-size:13px;">Paperklip - Autonomous B2B Outreach</span></p>

</body></html>
"""
