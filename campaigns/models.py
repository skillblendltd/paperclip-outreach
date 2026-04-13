import uuid
from django.db import models
from django.contrib.auth.models import User


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organization(BaseModel):
    """Top-level tenant. All data scopes through this."""
    name = models.CharField(max_length=300)
    slug = models.SlugField(max_length=100, unique=True)
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='organizations')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'organizations'
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(BaseModel):
    """Product line within an organization. Replaces Campaign.product CharField."""
    SLUG_CHOICES = [
        ('taggiq', 'TaggIQ'),
        ('kritno', 'Kritno'),
        ('fullypromoted', 'Fully Promoted'),
        ('other', 'Other'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=300)
    slug = models.SlugField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'products'
        unique_together = [('organization', 'slug')]
        ordering = ['organization', 'name']

    def __str__(self):
        return f'{self.organization.name} / {self.name}'


class Campaign(BaseModel):
    PRODUCT_CHOICES = [
        ('taggiq', 'TaggIQ'),
        ('kritno', 'Kritno'),
        ('fullypromoted', 'Fully Promoted'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=300, unique=True)
    product = models.CharField(max_length=30, choices=PRODUCT_CHOICES, default='taggiq',
        help_text='Legacy - use product_ref FK instead')
    product_ref = models.ForeignKey(
        Product, null=True, blank=True, on_delete=models.CASCADE, related_name='campaigns',
        help_text='Product this campaign belongs to (new FK)',
    )

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

    # Send window (DB-configurable, replaces hardcoded per-script logic)
    send_window_timezone = models.CharField(max_length=50, default='Europe/Dublin', help_text='Timezone for send window')
    send_window_start_hour = models.IntegerField(default=10, help_text='Earliest hour to send (0-23)')
    send_window_end_hour = models.IntegerField(default=17, help_text='Latest hour to send (0-23)')
    send_window_days = models.CharField(max_length=20, default='0,1,2,3,4', help_text='Comma-separated weekday numbers (0=Mon)')
    batch_size = models.IntegerField(default=100, help_text='Max prospects to process per run')
    inter_send_delay_min = models.IntegerField(default=5, help_text='Min seconds between sends')
    inter_send_delay_max = models.IntegerField(default=60, help_text='Max seconds between sends')
    priority_cities = models.CharField(max_length=500, blank=True, default='', help_text='Comma-separated cities to send first')

    class Meta:
        db_table = 'campaigns'
        ordering = ['name']

    def __str__(self):
        product_label = self.product_ref.slug if self.product_ref else self.product
        status = 'ON' if self.sending_enabled else 'OFF'
        return f'{self.name} [{product_label}] - {status}'


class Prospect(BaseModel):
    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('engaged', 'Engaged'),
        ('interested', 'Interested'),
        ('demo_scheduled', 'Demo Scheduled'),
        ('design_partner', 'Design Partner'),
        ('customer', 'Customer'),
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

    # TaggIQ integration fields (populated by webhook)
    taggiq_user_id = models.IntegerField(null=True, blank=True, db_index=True)
    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_expires_at = models.DateTimeField(null=True, blank=True)

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


class ScriptInsight(BaseModel):
    """AI-generated analysis of call transcripts to improve the calling script."""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='script_insights')
    calls_analyzed = models.IntegerField(default=0)
    date_range = models.CharField(max_length=100, blank=True, default='')

    # Analysis results
    answer_rate = models.FloatField(default=0, help_text='% of calls answered')
    interest_rate = models.FloatField(default=0, help_text='% of answered calls showing interest')
    demo_rate = models.FloatField(default=0, help_text='% of answered calls booking demo')

    top_objections = models.TextField(blank=True, default='', help_text='Most common objections')
    drop_off_points = models.TextField(blank=True, default='', help_text='Where prospects disengage')
    working_hooks = models.TextField(blank=True, default='', help_text='What language/hooks get engagement')
    prospect_language = models.TextField(blank=True, default='', help_text='Actual words prospects use to describe pain')
    suggestions = models.TextField(blank=True, default='', help_text='Specific script change recommendations')

    # Updated prompt
    suggested_prompt = models.TextField(blank=True, default='', help_text='Full suggested system prompt')
    prompt_applied = models.BooleanField(default=False, help_text='Whether this prompt was pushed to Vapi')
    applied_at = models.DateTimeField(null=True, blank=True)

    # Learning loop tracking
    baseline_answer_rate = models.FloatField(null=True, blank=True, help_text='Answer rate before prompt change')
    baseline_interest_rate = models.FloatField(null=True, blank=True, help_text='Interest rate before prompt change')
    post_change_answer_rate = models.FloatField(null=True, blank=True, help_text='Answer rate 1 week after change')
    post_change_interest_rate = models.FloatField(null=True, blank=True, help_text='Interest rate 1 week after change')
    improvement_measured = models.BooleanField(default=False, help_text='Whether post-change measurement was done')
    measured_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'script_insights'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.campaign.name} - {self.calls_analyzed} calls - {self.created_at:%Y-%m-%d}'


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

    # Cross-cron AI retry budget. Incremented by send_ai_reply on every attempt.
    # When ai_attempt_count >= 5 we stop trying to auto-reply to this inbound and
    # leave it for manual review (handle_replies skips it, dashboard surfaces it).
    ai_attempt_count = models.IntegerField(
        default=0,
        help_text='How many times the AI reply pipeline has tried to handle this inbound (success or fail).',
    )

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

    email = models.EmailField()
    product = models.ForeignKey(
        Product, null=True, blank=True, on_delete=models.CASCADE, related_name='suppressions',
        help_text='Product scope. Null = global suppression across all products.',
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'suppressions'
        ordering = ['-created_at']
        unique_together = [('email', 'product')]

    def __str__(self):
        scope = self.product.slug if self.product else 'GLOBAL'
        return f'{self.email} - {self.reason} [{scope}]'


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
        return f'{self.campaign.name} - {self.get_classification_display()} reply'


class EmailTemplate(BaseModel):
    """DB-driven email template. One row per campaign + sequence + variant."""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='email_templates')
    sequence_number = models.IntegerField(help_text='Sequence number (1-5)')
    ab_variant = models.CharField(max_length=1, choices=[('A', 'A'), ('B', 'B')])
    subject_template = models.CharField(
        max_length=500,
        help_text='Subject line. Variables: {{FNAME}}, {{COMPANY}}, {{CITY}}, {{YEAR}}, {{SEGMENT}}',
    )
    body_html_template = models.TextField(
        help_text='HTML body. Variables: {{FNAME}}, {{COMPANY}}, {{CITY}}, {{YEAR}}, {{SEGMENT}}',
    )
    template_name = models.CharField(max_length=100, help_text='Identifier logged in EmailLog.template_name')
    sequence_label = models.CharField(max_length=100, blank=True, default='', help_text='Human label, e.g. "Peer Story"')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'email_templates'
        unique_together = [('campaign', 'sequence_number', 'ab_variant')]
        ordering = ['campaign', 'sequence_number', 'ab_variant']

    def __str__(self):
        return f'{self.campaign.name} - Seq {self.sequence_number}{self.ab_variant}'


class CallScript(BaseModel):
    """Per-segment first message for Vapi calls. Replaces hardcoded first_messages in call_service.py."""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='call_scripts')
    segment = models.CharField(
        max_length=30, choices=Prospect.SEGMENT_CHOICES, blank=True, default='',
        help_text='Prospect segment. Empty = default script for this campaign.',
    )
    first_message = models.TextField(help_text='Vapi first_message override for this segment')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'call_scripts'
        unique_together = [('campaign', 'segment')]
        ordering = ['campaign', 'segment']

    def __str__(self):
        seg = self.segment or 'default'
        return f'{self.campaign.name} - {seg}'


class PromptTemplate(BaseModel):
    """DB-managed AI prompts per product. Enables per-tenant prompt customization."""

    FEATURE_CHOICES = [
        ('email_reply', 'Email Reply Generation'),
        ('call_analysis', 'Call Transcript Analysis'),
        ('script_improvement', 'Script Improvement'),
        ('classification', 'Email Classification'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='prompt_templates')
    feature = models.CharField(max_length=30, choices=FEATURE_CHOICES)
    name = models.CharField(max_length=300, help_text='Human name, e.g. "TaggIQ Email Expert v3"')
    system_prompt = models.TextField(help_text='Full system prompt for the AI model')
    model = models.CharField(max_length=100, default='claude-sonnet-4-6', help_text='Model ID to use')
    max_tokens = models.IntegerField(default=4096)
    temperature = models.FloatField(default=0.7)
    is_active = models.BooleanField(default=True)
    version = models.IntegerField(default=1, help_text='Increment on each update for tracking')
    # --- persona / reply-engine metadata (used by send_ai_reply + audit detectors) ---
    from_name = models.CharField(
        max_length=200, blank=True, default='',
        help_text='Display name for outbound replies, e.g. "Lisa - Fully Promoted Dublin"',
    )
    signature_name = models.CharField(
        max_length=100, blank=True, default='',
        help_text='First-name anchor for signature stripping in detectors, e.g. "Lisa"',
    )
    max_reply_words = models.IntegerField(
        default=130,
        help_text='Hard ceiling on reply body word count (signature excluded). Pre-send block fires above this.',
    )
    warn_reply_words = models.IntegerField(
        default=100,
        help_text='Soft warn threshold for reply length. Logged but not blocked.',
    )

    class Meta:
        db_table = 'prompt_templates'
        ordering = ['product', 'feature', '-version']

    def __str__(self):
        return f'{self.name} (v{self.version})'


class AIUsageLog(BaseModel):
    """Tracks every AI call for cost allocation and observability."""

    FEATURE_CHOICES = [
        ('email_reply', 'Email Reply'),
        ('call_analysis', 'Call Analysis'),
        ('script_improvement', 'Script Improvement'),
        ('classification', 'Classification'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='ai_usage_logs')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='ai_usage_logs')
    campaign = models.ForeignKey(Campaign, null=True, blank=True, on_delete=models.SET_NULL, related_name='ai_usage_logs')
    prospect = models.ForeignKey('Prospect', null=True, blank=True, on_delete=models.SET_NULL, related_name='ai_usage_logs')

    feature = models.CharField(max_length=30, choices=FEATURE_CHOICES)
    model = models.CharField(max_length=100, help_text='Model ID used')
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    latency_ms = models.IntegerField(default=0)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True, default='')
    prompt_version = models.IntegerField(null=True, blank=True, help_text='PromptTemplate.version used')

    class Meta:
        db_table = 'ai_usage_log'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'created_at']),
            models.Index(fields=['product', 'feature']),
        ]

    def __str__(self):
        return f'{self.feature} - {self.model} - ${self.cost_usd}'


# SocialAccount, SocialPost, SocialPostDelivery moved to social_studio app in
# social-studio-v1 (2026-04-11). DB tables unchanged — ownership moved via
# SeparateDatabaseAndState. See docs/social-studio-v1-plan.md.


class WebhookEvent(BaseModel):
    """Incoming webhook events for idempotent processing."""

    delivery_id = models.CharField(max_length=100, unique=True, db_index=True)
    source = models.CharField(max_length=50, default='taggiq')
    event_type = models.CharField(max_length=50)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    error = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'webhook_events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_type', 'processed']),
        ]

    def __str__(self):
        status = 'OK' if self.processed else 'PENDING'
        return f'{self.event_type} ({self.delivery_id[:8]}) [{status}]'
