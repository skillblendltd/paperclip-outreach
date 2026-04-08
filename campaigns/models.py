import uuid
from django.db import models


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Campaign(BaseModel):
    PRODUCT_CHOICES = [
        ('taggiq', 'TaggIQ'),
        ('kritno', 'Kritno'),
        ('fullypromoted', 'Fully Promoted'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=300, unique=True)
    product = models.CharField(max_length=30, choices=PRODUCT_CHOICES, default='taggiq')

    # Sender settings
    from_name = models.CharField(max_length=200, default='', help_text='Sender display name')
    from_email = models.EmailField(default='', help_text='Sender email (must be SES-verified)')
    reply_to_email = models.EmailField(blank=True, default='', help_text='Reply-to address')

    # Safeguards
    sending_enabled = models.BooleanField(default=False, help_text='Master switch for this campaign')
    max_emails_per_day = models.IntegerField(default=15)
    min_gap_minutes = models.IntegerField(default=15)
    max_emails_per_prospect = models.IntegerField(default=5)
    require_sequence_order = models.BooleanField(default=True)

    follow_up_days = models.IntegerField(
        default=5,
        help_text='Days to wait before sending next sequence email',
    )

    unsubscribe_footer_html = models.TextField(
        default='<p style="font-size:12px;color:#999;margin-top:30px;">'
                'If you\'d prefer not to hear from us, simply reply with '
                '"unsubscribe" and we\'ll remove you immediately.</p>',
    )

    # Auto-reply safeguard
    auto_reply_enabled = models.BooleanField(
        default=False,
        help_text='Enable autonomous auto-replies for interested/question/other classifications',
    )

    # Call settings
    calling_enabled = models.BooleanField(default=False, help_text='Enable outbound calling for this campaign')
    max_calls_per_day = models.IntegerField(default=20, help_text='Max calls per day for this campaign')
    min_gap_call_minutes = models.IntegerField(default=1, help_text='Min minutes between calls')
    max_calls_per_prospect = models.IntegerField(default=3, help_text='Max call attempts per prospect')
    vapi_assistant_id = models.CharField(max_length=100, blank=True, default='', help_text='Vapi assistant ID for outbound calls')

    class Meta:
        db_table = 'campaigns'
        ordering = ['name']

    def __str__(self):
        status = 'ON' if self.sending_enabled else 'OFF'
        return f'{self.name} [{self.product}] — {status}'


class Prospect(BaseModel):
    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('engaged', 'Engaged'),
        ('interested', 'Interested'),
        ('demo_scheduled', 'Demo Scheduled'),
        ('design_partner', 'Design Partner'),
        ('not_interested', 'Not Interested'),
        ('opted_out', 'Opted Out'),
        ('follow_up_later', 'Follow Up Later'),
    ]

    TIER_CHOICES = [
        ('A', 'Tier A - Hot'),
        ('B', 'Tier B - Warm'),
        ('C', 'Tier C - Cool'),
        ('D', 'Tier D - Park'),
    ]

    SEGMENT_CHOICES = [
        ('print_shop', 'Print Shop'),
        ('promo_distributor', 'Promo Distributor'),
        ('apparel_embroidery', 'Apparel / Embroidery'),
        ('mixed', 'Mixed Operations'),
        ('signs', 'Signs & Display'),
        ('print_agency', 'Print & Creative Agency'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='prospects')

    # Core
    business_name = models.CharField(max_length=300)
    website = models.URLField(blank=True, default='')
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')
    city = models.CharField(max_length=200, blank=True, default='')
    region = models.CharField(max_length=200, blank=True, default='')

    # Decision maker
    decision_maker_name = models.CharField(max_length=300, blank=True, default='')
    decision_maker_title = models.CharField(max_length=200, blank=True, default='')

    # Classification
    business_type = models.CharField(max_length=100, blank=True, default='')
    segment = models.CharField(max_length=30, choices=SEGMENT_CHOICES, blank=True, default='')
    tier = models.CharField(max_length=1, choices=TIER_CHOICES, blank=True, default='C')
    score = models.IntegerField(default=0)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    emails_sent = models.IntegerField(default=0)
    last_emailed_at = models.DateTimeField(null=True, blank=True)
    calls_sent = models.IntegerField(default=0)
    last_called_at = models.DateTimeField(null=True, blank=True)

    # Extra
    current_tools = models.CharField(max_length=500, blank=True, default='')
    pain_signals = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')

    follow_up_after = models.DateField(null=True, blank=True, help_text='Date to follow up with this prospect')

    send_enabled = models.BooleanField(default=True, help_text='Uncheck to block outreach')
    best_practices_group = models.BooleanField(default=False, help_text='Member of BNI best practices community group')

    class Meta:
        db_table = 'prospects'
        ordering = ['-score', 'business_name']
        unique_together = [('campaign', 'email')]
        indexes = [
            models.Index(fields=['tier', 'status']),
            models.Index(fields=['email']),
            models.Index(fields=['segment']),
        ]

    def __str__(self):
        return f'{self.business_name} ({self.tier}/{self.score}) - {self.status}'


class EmailLog(BaseModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='email_logs')
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='email_logs')
    to_email = models.EmailField()
    subject = models.CharField(max_length=500)
    body_html = models.TextField()
    sequence_number = models.IntegerField(default=1)
    template_name = models.CharField(max_length=100, blank=True, default='')

    status = models.CharField(
        max_length=20,
        choices=[('sent', 'Sent'), ('failed', 'Failed'), ('blocked', 'Blocked')],
        default='sent',
    )
    ses_message_id = models.CharField(max_length=255, blank=True, default='')
    error_message = models.TextField(blank=True, default='')

    ab_variant = models.CharField(max_length=10, blank=True, default='')
    triggered_by = models.CharField(max_length=50, default='agent')

    class Meta:
        db_table = 'email_log'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['prospect', 'sequence_number']),
            models.Index(fields=['to_email', 'created_at']),
            models.Index(fields=['campaign', 'ab_variant']),
        ]

    def __str__(self):
        return f'{self.to_email} - seq {self.sequence_number} - {self.status}'


class CallLog(BaseModel):
    """Log of outbound calls placed via Vapi."""
    STATUS_CHOICES = [
        ('placed', 'Placed'),
        ('answered', 'Answered'),
        ('voicemail', 'Voicemail'),
        ('no_answer', 'No Answer'),
        ('busy', 'Busy'),
        ('failed', 'Failed'),
    ]
    DISPOSITION_CHOICES = [
        ('interested', 'Interested'),
        ('demo_booked', 'Demo Booked'),
        ('send_info', 'Send Info'),
        ('callback_requested', 'Callback Requested'),
        ('not_interested', 'Not Interested'),
        ('already_using_tool', 'Already Using Tool'),
        ('wrong_number', 'Wrong Number'),
        ('gatekeeper_blocked', 'Gatekeeper Blocked'),
        ('do_not_call', 'Do Not Call'),
        ('pending', 'Pending'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='call_logs')
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='call_logs')
    phone_number = models.CharField(max_length=50)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='placed')
    disposition = models.CharField(max_length=30, choices=DISPOSITION_CHOICES, default='pending')

    call_duration = models.IntegerField(default=0, help_text='Duration in seconds')
    vapi_call_id = models.CharField(max_length=100, blank=True, default='', help_text='Vapi call ID')
    recording_url = models.URLField(blank=True, default='')
    transcript = models.TextField(blank=True, default='')
    summary = models.TextField(blank=True, default='', help_text='AI-generated call summary')

    email_captured = models.EmailField(blank=True, default='', help_text='Email captured during call')
    callback_time = models.CharField(max_length=100, blank=True, default='', help_text='Requested callback time')
    current_tools = models.CharField(max_length=500, blank=True, default='', help_text='Tools prospect mentioned')
    pain_signals = models.TextField(blank=True, default='', help_text='Pain points mentioned')

    triggered_by = models.CharField(max_length=50, default='management_command')

    class Meta:
        db_table = 'call_log'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['prospect', 'created_at']),
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['vapi_call_id']),
        ]

    def __str__(self):
        return f'{self.phone_number} - {self.status} - {self.disposition}'


class EmailQueue(BaseModel):
    """
    Staged emails for future sending. Agent queues emails here,
    process_queue management command sends them when due.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('skipped', 'Skipped'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='queued_emails')
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='queued_emails')
    subject = models.CharField(max_length=500)
    body_html = models.TextField()
    sequence_number = models.IntegerField(default=1)
    template_name = models.CharField(max_length=100, blank=True, default='')
    ab_variant = models.CharField(max_length=10, blank=True, default='')

    send_after = models.DateTimeField(help_text='Do not send before this time')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'email_queue'
        ordering = ['send_after']
        indexes = [
            models.Index(fields=['status', 'send_after']),
            models.Index(fields=['campaign', 'prospect', 'sequence_number']),
        ]

    def __str__(self):
        return f'{self.prospect.email} seq={self.sequence_number} send_after={self.send_after} [{self.status}]'


class InboundEmail(BaseModel):
    """Inbound email replies captured from Zoho IMAP."""

    CLASSIFICATION_CHOICES = [
        ('interested', 'Interested'),
        ('not_interested', 'Not Interested'),
        ('opt_out', 'Opt Out'),
        ('question', 'Question'),
        ('out_of_office', 'Out of Office'),
        ('bounce', 'Bounce'),
        ('other', 'Other'),
    ]

    prospect = models.ForeignKey('Prospect', null=True, blank=True, on_delete=models.SET_NULL, related_name='inbound_emails')
    campaign = models.ForeignKey('Campaign', null=True, blank=True, on_delete=models.SET_NULL, related_name='inbound_emails')

    from_email = models.EmailField()
    from_name = models.CharField(max_length=300, blank=True, default='')
    subject = models.CharField(max_length=500)
    body_text = models.TextField(default='')
    message_id = models.CharField(max_length=500, unique=True)
    in_reply_to = models.CharField(max_length=500, blank=True, default='')

    classification = models.CharField(max_length=20, choices=CLASSIFICATION_CHOICES, default='other')
    replied_to_sequence = models.IntegerField(null=True, blank=True)

    needs_reply = models.BooleanField(default=False)
    replied = models.BooleanField(default=False)
    auto_replied = models.BooleanField(default=False, help_text='True if reply was sent by auto-reply system')
    reply_sent_at = models.DateTimeField(null=True, blank=True)
    status_updated = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')

    received_at = models.DateTimeField()

    class Meta:
        db_table = 'inbound_emails'
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['from_email']),
            models.Index(fields=['classification', 'needs_reply']),
        ]

    def __str__(self):
        return f'{self.from_email} - {self.classification} - {self.subject[:50]}'


class MailboxConfig(BaseModel):
    """IMAP/SMTP credentials per campaign for multi-mailbox reply monitoring."""

    campaign = models.OneToOneField(
        Campaign, on_delete=models.CASCADE, related_name='mailbox',
        help_text='Campaign this mailbox monitors replies for',
    )

    # IMAP (reading replies)
    imap_host = models.CharField(max_length=200, default='imappro.zoho.eu')
    imap_port = models.IntegerField(default=993)
    imap_email = models.EmailField(help_text='Email address to check for replies')
    imap_password = models.CharField(max_length=500)

    # SMTP (sending replies back)
    smtp_host = models.CharField(max_length=200, default='smtppro.zoho.eu')
    smtp_port = models.IntegerField(default=465)
    smtp_email = models.EmailField(help_text='Email address to send replies from')
    smtp_password = models.CharField(max_length=500)

    is_active = models.BooleanField(default=True, help_text='Enable monitoring for this mailbox')
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'mailbox_configs'
        ordering = ['campaign__name']

    def __str__(self):
        status = 'ON' if self.is_active else 'OFF'
        return f'{self.campaign.name} <{self.imap_email}> [{status}]'

    def get_smtp_config(self):
        """Return SMTP config dict for EmailService.send_reply()."""
        return {
            'host': self.smtp_host,
            'port': self.smtp_port,
            'email': self.smtp_email,
            'password': self.smtp_password,
        }


class Suppression(BaseModel):
    REASON_CHOICES = [
        ('opt_out', 'Opted Out'),
        ('bounce', 'Bounced'),
        ('complaint', 'Complaint'),
        ('manual', 'Manually Added'),
    ]

    email = models.EmailField(unique=True)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'suppressions'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} - {self.reason}'


class ReplyTemplate(BaseModel):
    """
    Pre-configured auto-reply templates per campaign + classification.
    Variables: {{FNAME}}, {{COMPANY}}, {{CITY}}, {{SEGMENT}},
               {{ORIGINAL_SUBJECT}}, {{ORIGINAL_BODY_SHORT}}
    """

    CLASSIFICATION_CHOICES = [
        ('interested', 'Interested'),
        ('question', 'Question'),
        ('other', 'Other'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='reply_templates')
    classification = models.CharField(max_length=20, choices=CLASSIFICATION_CHOICES)
    subject_template = models.CharField(
        max_length=500,
        default='Re: {{ORIGINAL_SUBJECT}}',
        help_text='Subject line template. Variables: {{ORIGINAL_SUBJECT}}',
    )
    body_html_template = models.TextField(
        help_text='HTML body template. Variables: {{FNAME}}, {{COMPANY}}, {{CITY}}, '
                  '{{SEGMENT}}, {{ORIGINAL_SUBJECT}}, {{ORIGINAL_BODY_SHORT}}',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'reply_templates'
        unique_together = [('campaign', 'classification')]
        ordering = ['campaign', 'classification']

    def __str__(self):
        return f'{self.campaign.name} — {self.get_classification_display()} reply'
