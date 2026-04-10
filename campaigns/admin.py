"""
Django Admin for Paperclip Outreach.
Multi-product outreach pipeline: TaggIQ, Fully Promoted, Kritno.
"""
import csv
import io
from django.contrib import admin
from django.utils.html import format_html
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Count, Q

from .models import (
    Organization, Product, Campaign, Prospect, EmailLog, EmailQueue,
    Suppression, InboundEmail, ReplyTemplate, MailboxConfig, CallLog,
    ScriptInsight, EmailTemplate, CallScript, PromptTemplate, AIUsageLog,
    WebhookEvent,
)
from .forms import CsvUploadForm


# Product colour scheme — used throughout admin for visual separation
PRODUCT_COLOURS = {
    'taggiq': '#3498db',
    'fullypromoted': '#e67e22',
    'kritno': '#9b59b6',
    'other': '#95a5a6',
}

PRODUCT_LABELS = {
    'taggiq': 'TaggIQ',
    'fullypromoted': 'Fully Promoted',
    'kritno': 'Kritno',
    'other': 'Other',
}


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'product_count', 'created_at']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}

    @admin.display(description='Products')
    def product_count(self, obj):
        return obj.products.count()


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'organization', 'is_active', 'campaign_count']
    list_filter = ['organization', 'is_active']
    search_fields = ['name', 'slug']

    @admin.display(description='Campaigns')
    def campaign_count(self, obj):
        return obj.campaigns.count()


class EmailTemplateInline(admin.TabularInline):
    model = EmailTemplate
    extra = 0
    fields = ['sequence_number', 'ab_variant', 'sequence_label', 'subject_template', 'is_active']
    ordering = ['sequence_number', 'ab_variant']


class MailboxConfigInline(admin.StackedInline):
    model = MailboxConfig
    extra = 0
    max_num = 1
    fields = ['imap_host', 'imap_port', 'imap_email', 'imap_password',
              'smtp_host', 'smtp_port', 'smtp_email', 'smtp_password', 'is_active']

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in ('imap_password', 'smtp_password'):
            from django.forms import PasswordInput
            kwargs['widget'] = PasswordInput(render_value=True)
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'product_badge', 'sending_status', 'from_email',
        'prospect_count', 'template_count', 'max_emails_per_day', 'min_gap_minutes',
    ]
    list_filter = ['product_ref__slug', 'sending_enabled']
    search_fields = ['name']
    inlines = [EmailTemplateInline, MailboxConfigInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'product_ref', 'product')
        }),
        ('Sender', {
            'fields': ('from_name', 'from_email', 'reply_to_email')
        }),
        ('Safeguards', {
            'fields': (
                'sending_enabled', 'auto_reply_enabled', 'max_emails_per_day',
                'min_gap_minutes', 'max_emails_per_prospect',
                'require_sequence_order', 'follow_up_days',
            )
        }),
        ('Send Window', {
            'fields': (
                'send_window_timezone', 'send_window_start_hour', 'send_window_end_hour',
                'send_window_days', 'batch_size', 'inter_send_delay_min',
                'inter_send_delay_max', 'priority_cities',
            ),
            'classes': ('collapse',),
        }),
        ('Calling', {
            'fields': ('calling_enabled', 'max_calls_per_day', 'min_gap_call_minutes',
                       'max_calls_per_prospect', 'vapi_assistant_id'),
            'classes': ('collapse',),
        }),
        ('Footer', {
            'fields': ('unsubscribe_footer_html',),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _prospect_count=Count('prospects', distinct=True),
            _template_count=Count('email_templates', distinct=True),
        )

    @admin.display(description='Templates', ordering='_template_count')
    def template_count(self, obj):
        count = obj._template_count
        if count == 0:
            return format_html('<span style="color:#e74c3c;font-weight:bold">0</span>')
        return count

    @admin.display(description='Product')
    def product_badge(self, obj):
        slug = obj.product_ref.slug if obj.product_ref else obj.product
        colour = PRODUCT_COLOURS.get(slug, '#95a5a6')
        label = PRODUCT_LABELS.get(slug, slug)
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;'
            'border-radius:3px;font-weight:bold;font-size:11px">{}</span>',
            colour, label
        )

    @admin.display(description='Prospects', ordering='_prospect_count')
    def prospect_count(self, obj):
        return obj._prospect_count

    @admin.display(description='Sending')
    def sending_status(self, obj):
        if obj.sending_enabled:
            return format_html(
                '<span style="background:#27ae60;color:#fff;padding:4px 12px;'
                'border-radius:3px;font-weight:bold">ON</span>'
            )
        return format_html(
            '<span style="background:#e74c3c;color:#fff;padding:4px 12px;'
            'border-radius:3px;font-weight:bold">OFF</span>'
        )


# CSV column mapping: CSV header -> model field
CSV_COLUMN_MAP = {
    'business_name': 'business_name',
    'company': 'business_name',
    'name': 'business_name',
    'email': 'email',
    'email_address': 'email',
    'website': 'website',
    'url': 'website',
    'phone': 'phone',
    'telephone': 'phone',
    'city': 'city',
    'region': 'region',
    'state': 'region',
    'province': 'region',
    'decision_maker_name': 'decision_maker_name',
    'contact_name': 'decision_maker_name',
    'contact': 'decision_maker_name',
    'decision_maker_title': 'decision_maker_title',
    'title': 'decision_maker_title',
    'business_type': 'business_type',
    'type': 'business_type',
    'segment': 'segment',
    'tier': 'tier',
    'score': 'score',
    'current_tools': 'current_tools',
    'tools': 'current_tools',
    'pain_signals': 'pain_signals',
    'notes': 'notes',
}


class ProductListFilter(admin.SimpleListFilter):
    """Top-level product filter — appears first in the sidebar."""
    title = 'product'
    parameter_name = 'product'

    def lookups(self, request, model_admin):
        return [
            ('taggiq', 'TaggIQ'),
            ('fullypromoted', 'Fully Promoted'),
            ('kritno', 'Kritno'),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(campaign__product=self.value())
        return queryset


@admin.register(Prospect)
class ProspectAdmin(admin.ModelAdmin):
    list_display = [
        'business_name', 'product_badge', 'campaign', 'tier_badge', 'score',
        'status_badge', 'email', 'decision_maker_name',
        'city', 'emails_sent', 'last_emailed_at', 'calls_sent', 'last_called_at',
        'send_enabled', 'best_practices_group',
    ]
    list_filter = [ProductListFilter, 'campaign', 'tier', 'status', 'segment', 'send_enabled', 'best_practices_group', 'region', 'emails_sent']
    search_fields = ['business_name', 'email', 'decision_maker_name', 'city', 'region']
    list_editable = ['send_enabled', 'best_practices_group']
    list_select_related = ['campaign']
    readonly_fields = ['emails_sent', 'last_emailed_at', 'calls_sent', 'last_called_at', 'created_at', 'updated_at']
    list_per_page = 50
    ordering = ['-score']

    fieldsets = (
        ('Campaign', {
            'fields': ('campaign',)
        }),
        ('Business', {
            'fields': ('business_name', 'website', 'email', 'phone', 'city', 'region')
        }),
        ('Decision Maker', {
            'fields': ('decision_maker_name', 'decision_maker_title')
        }),
        ('Classification', {
            'fields': ('business_type', 'segment', 'tier', 'score')
        }),
        ('Outreach Status', {
            'fields': ('status', 'send_enabled', 'best_practices_group', 'emails_sent', 'last_emailed_at', 'calls_sent', 'last_called_at')
        }),
        ('Intel', {
            'fields': ('current_tools', 'pain_signals', 'notes'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Product')
    def product_badge(self, obj):
        product = obj.campaign.product
        colour = PRODUCT_COLOURS.get(product, '#95a5a6')
        label = PRODUCT_LABELS.get(product, product)
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:10px;font-weight:bold">{}</span>',
            colour, label
        )

    actions = [
        'enable_sending', 'disable_sending',
        'enable_calling',
        'mark_interested', 'mark_demo_scheduled', 'mark_design_partner',
        'mark_not_interested', 'mark_opted_out',
        'mark_new', 'mark_contacted', 'mark_engaged',
        'add_to_suppression',
        'upload_csv',
    ]

    @admin.display(description='Tier')
    def tier_badge(self, obj):
        colours = {'A': '#e74c3c', 'B': '#f39c12', 'C': '#3498db', 'D': '#95a5a6'}
        colour = colours.get(obj.tier, '#95a5a6')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-weight:bold">{}</span>',
            colour, obj.tier
        )

    @admin.display(description='Status')
    def status_badge(self, obj):
        colours = {
            'new': '#3498db', 'contacted': '#9b59b6', 'engaged': '#f39c12',
            'interested': '#27ae60', 'demo_scheduled': '#2ecc71',
            'design_partner': '#1abc9c', 'not_interested': '#e74c3c',
            'opted_out': '#95a5a6',
        }
        colour = colours.get(obj.status, '#95a5a6')
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;'
            'border-radius:3px;font-size:11px">{}</span>',
            colour, obj.get_status_display()
        )

    @admin.action(description='Enable sending for selected')
    def enable_sending(self, request, queryset):
        updated = queryset.update(send_enabled=True)
        self.message_user(request, f'{updated} prospect(s) sending enabled.')

    @admin.action(description='Disable sending for selected')
    def disable_sending(self, request, queryset):
        updated = queryset.update(send_enabled=False)
        self.message_user(request, f'{updated} prospect(s) sending disabled.')

    @admin.action(description='Enable calling (set send_enabled=True + reset calls_sent)')
    def enable_calling(self, request, queryset):
        queryset.update(send_enabled=True, calls_sent=0)

    @admin.action(description='Set status: Interested')
    def mark_interested(self, request, queryset):
        updated = queryset.update(status='interested')
        self.message_user(request, f'{updated} prospect(s) marked as Interested.')

    @admin.action(description='Set status: Demo Scheduled')
    def mark_demo_scheduled(self, request, queryset):
        updated = queryset.update(status='demo_scheduled')
        self.message_user(request, f'{updated} prospect(s) marked as Demo Scheduled.')

    @admin.action(description='Set status: Design Partner')
    def mark_design_partner(self, request, queryset):
        updated = queryset.update(status='design_partner')
        self.message_user(request, f'{updated} prospect(s) marked as Design Partner.')

    @admin.action(description='Set status: Not Interested')
    def mark_not_interested(self, request, queryset):
        updated = queryset.update(status='not_interested', send_enabled=False)
        self.message_user(request, f'{updated} prospect(s) marked as Not Interested (sending disabled).')

    @admin.action(description='Set status: Opted Out (+ suppress)')
    def mark_opted_out(self, request, queryset):
        count = 0
        for prospect in queryset:
            prospect.status = 'opted_out'
            prospect.send_enabled = False
            prospect.save()
            Suppression.objects.get_or_create(
                email=prospect.email,
                defaults={'reason': 'opt_out', 'notes': f'Bulk opted out from admin'}
            )
            count += 1
        self.message_user(request, f'{count} prospect(s) opted out and added to suppression list.')

    @admin.action(description='Set status: New')
    def mark_new(self, request, queryset):
        updated = queryset.update(status='new')
        self.message_user(request, f'{updated} prospect(s) reset to New.')

    @admin.action(description='Set status: Contacted')
    def mark_contacted(self, request, queryset):
        updated = queryset.update(status='contacted')
        self.message_user(request, f'{updated} prospect(s) marked as Contacted.')

    @admin.action(description='Set status: Engaged')
    def mark_engaged(self, request, queryset):
        updated = queryset.update(status='engaged')
        self.message_user(request, f'{updated} prospect(s) marked as Engaged.')

    @admin.action(description='Add to suppression list')
    def add_to_suppression(self, request, queryset):
        count = 0
        for prospect in queryset:
            if prospect.email:
                Suppression.objects.get_or_create(
                    email=prospect.email,
                    defaults={'reason': 'manual', 'notes': f'Added from admin bulk action'}
                )
                prospect.send_enabled = False
                prospect.save()
                count += 1
        self.message_user(request, f'{count} email(s) added to suppression list.')

    @admin.action(description='Upload CSV of prospects')
    def upload_csv(self, request, queryset):
        if 'apply' in request.POST:
            form = CsvUploadForm(request.POST, request.FILES)
            if form.is_valid():
                campaign_id = request.POST.get('campaign_id')
                try:
                    campaign = Campaign.objects.get(id=campaign_id)
                except Campaign.DoesNotExist:
                    self.message_user(request, 'Campaign not found.', messages.ERROR)
                    return redirect(request.get_full_path())

                csv_file = request.FILES['csv_file']
                decoded = csv_file.read().decode('utf-8-sig')
                reader = csv.DictReader(io.StringIO(decoded))

                created = 0
                updated = 0
                skipped = 0

                for row in reader:
                    mapped = {}
                    for csv_col, value in row.items():
                        if not csv_col:
                            continue
                        field = CSV_COLUMN_MAP.get(csv_col.strip().lower().replace(' ', '_'))
                        if field:
                            mapped[field] = value.strip() if value else ''

                    if not mapped.get('business_name'):
                        skipped += 1
                        continue

                    email = mapped.get('email', '')
                    existing = None
                    if email:
                        existing = Prospect.objects.filter(
                            campaign=campaign, email__iexact=email
                        ).first()

                    if existing:
                        for field, val in mapped.items():
                            if val and field != 'business_name':
                                if field == 'score':
                                    try:
                                        val = int(val)
                                    except (ValueError, TypeError):
                                        continue
                                setattr(existing, field, val)
                        existing.save()
                        updated += 1
                    else:
                        score_val = 0
                        if mapped.get('score'):
                            try:
                                score_val = int(mapped['score'])
                            except (ValueError, TypeError):
                                pass
                        Prospect.objects.create(
                            campaign=campaign,
                            business_name=mapped.get('business_name', ''),
                            email=email,
                            website=mapped.get('website', ''),
                            phone=mapped.get('phone', ''),
                            city=mapped.get('city', ''),
                            region=mapped.get('region', ''),
                            decision_maker_name=mapped.get('decision_maker_name', ''),
                            decision_maker_title=mapped.get('decision_maker_title', ''),
                            business_type=mapped.get('business_type', ''),
                            segment=mapped.get('segment', ''),
                            tier=mapped.get('tier', 'C') or 'C',
                            score=score_val,
                            current_tools=mapped.get('current_tools', ''),
                            pain_signals=mapped.get('pain_signals', ''),
                            notes=mapped.get('notes', ''),
                        )
                        created += 1

                self.message_user(
                    request,
                    f'CSV imported to "{campaign.name}": {created} created, {updated} updated, {skipped} skipped.',
                    messages.SUCCESS,
                )
                return redirect('admin:campaigns_prospect_changelist')

        form = CsvUploadForm()
        campaigns = Campaign.objects.all()
        return render(request, 'admin/csv_upload.html', {
            'form': form,
            'campaigns': campaigns,
            'title': 'Upload CSV of Prospects',
        })


class ProductLogFilter(admin.SimpleListFilter):
    title = 'product'
    parameter_name = 'product'

    def lookups(self, request, model_admin):
        return [('taggiq', 'TaggIQ'), ('fullypromoted', 'Fully Promoted'), ('kritno', 'Kritno')]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(campaign__product=self.value())
        return queryset


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'product_badge', 'campaign', 'prospect_name', 'to_email', 'subject',
        'sequence_number', 'template_name', 'ab_variant', 'status_badge', 'triggered_by',
    ]
    list_filter = [ProductLogFilter, 'campaign', 'status', 'sequence_number', 'ab_variant', 'triggered_by', 'template_name']
    list_select_related = ['campaign', 'prospect']
    search_fields = ['to_email', 'subject', 'prospect__business_name']
    readonly_fields = [
        'campaign', 'prospect', 'to_email', 'subject', 'body_html',
        'sequence_number', 'template_name', 'ab_variant', 'status',
        'ses_message_id', 'error_message', 'triggered_by',
        'created_at', 'updated_at',
    ]
    list_per_page = 50
    date_hierarchy = 'created_at'

    @admin.display(description='Product')
    def product_badge(self, obj):
        product = obj.campaign.product
        colour = PRODUCT_COLOURS.get(product, '#95a5a6')
        label = PRODUCT_LABELS.get(product, product)
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:10px;font-weight:bold">{}</span>',
            colour, label
        )

    @admin.display(description='Prospect')
    def prospect_name(self, obj):
        return obj.prospect.business_name

    @admin.display(description='Status')
    def status_badge(self, obj):
        colours = {'sent': '#27ae60', 'failed': '#e74c3c', 'blocked': '#f39c12'}
        colour = colours.get(obj.status, '#95a5a6')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px">{}</span>',
            colour, obj.status.upper()
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = [
        'phone_number', 'prospect_link', 'campaign_badge', 'status_badge',
        'disposition_badge', 'call_duration_display', 'summary_short',
        'email_captured', 'created_at',
    ]
    list_filter = ['status', 'disposition', 'campaign__product', 'campaign']
    search_fields = ['phone_number', 'prospect__business_name', 'transcript', 'summary']
    readonly_fields = [
        'campaign', 'prospect', 'phone_number', 'vapi_call_id',
        'status', 'disposition', 'call_duration', 'recording_url',
        'transcript', 'summary', 'email_captured', 'callback_time',
        'current_tools', 'pain_signals', 'triggered_by', 'created_at',
    ]
    list_per_page = 50
    date_hierarchy = 'created_at'

    def prospect_link(self, obj):
        return obj.prospect.business_name
    prospect_link.short_description = 'Business'

    def campaign_badge(self, obj):
        return obj.campaign.name
    campaign_badge.short_description = 'Campaign'

    def status_badge(self, obj):
        colors = {
            'placed': '#666', 'answered': '#28a745', 'voicemail': '#ffc107',
            'no_answer': '#6c757d', 'busy': '#fd7e14', 'failed': '#dc3545',
        }
        color = colors.get(obj.status, '#666')
        return format_html('<span style="color:{}; font-weight:bold;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = 'Status'

    def disposition_badge(self, obj):
        colors = {
            'interested': '#28a745', 'demo_booked': '#007bff', 'send_info': '#17a2b8',
            'not_interested': '#dc3545', 'callback_requested': '#ffc107',
            'already_using_tool': '#6c757d', 'pending': '#aaa',
        }
        color = colors.get(obj.disposition, '#666')
        return format_html('<span style="color:{};">{}</span>', color, obj.get_disposition_display())
    disposition_badge.short_description = 'Disposition'

    def call_duration_display(self, obj):
        if obj.call_duration:
            mins = obj.call_duration // 60
            secs = obj.call_duration % 60
            return f'{mins}:{secs:02d}'
        return '-'
    call_duration_display.short_description = 'Duration'

    def summary_short(self, obj):
        return obj.summary[:80] + '...' if len(obj.summary) > 80 else obj.summary
    summary_short.short_description = 'Summary'


@admin.register(EmailQueue)
class EmailQueueAdmin(admin.ModelAdmin):
    list_display = [
        'send_after', 'product_badge', 'campaign', 'prospect_name', 'prospect_email',
        'sequence_number', 'ab_variant', 'status_badge',
    ]
    list_filter = [ProductLogFilter, 'campaign', 'status', 'sequence_number']
    list_select_related = ['campaign', 'prospect']
    search_fields = ['prospect__business_name', 'prospect__email', 'subject']
    list_per_page = 50
    ordering = ['send_after']
    actions = ['cancel_selected']

    @admin.display(description='Product')
    def product_badge(self, obj):
        product = obj.campaign.product
        colour = PRODUCT_COLOURS.get(product, '#95a5a6')
        label = PRODUCT_LABELS.get(product, product)
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:10px;font-weight:bold">{}</span>',
            colour, label
        )

    @admin.display(description='Prospect')
    def prospect_name(self, obj):
        return obj.prospect.business_name

    @admin.display(description='Email')
    def prospect_email(self, obj):
        return obj.prospect.email

    @admin.display(description='Status')
    def status_badge(self, obj):
        colours = {
            'pending': '#3498db', 'sent': '#27ae60',
            'failed': '#e74c3c', 'cancelled': '#95a5a6', 'skipped': '#f39c12',
        }
        colour = colours.get(obj.status, '#95a5a6')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px">{}</span>',
            colour, obj.status.upper()
        )

    @admin.action(description='Cancel selected queued emails')
    def cancel_selected(self, request, queryset):
        updated = queryset.filter(status='pending').update(status='cancelled')
        self.message_user(request, f'{updated} queued email(s) cancelled.')


@admin.register(InboundEmail)
class InboundEmailAdmin(admin.ModelAdmin):
    list_display = [
        'received_at', 'from_email', 'prospect_link', 'campaign',
        'subject_short', 'classification_badge', 'needs_reply_badge',
        'replied_badge', 'auto_replied_badge',
    ]
    list_filter = [
        'classification', 'needs_reply', 'replied', 'auto_replied', 'campaign',
    ]
    list_select_related = ['prospect', 'campaign']
    search_fields = ['from_email', 'subject', 'body_text', 'from_name']
    readonly_fields = [
        'prospect', 'campaign', 'from_email', 'from_name', 'subject',
        'body_text', 'message_id', 'in_reply_to', 'classification',
        'replied_to_sequence', 'needs_reply', 'replied', 'auto_replied',
        'reply_sent_at', 'status_updated', 'notes', 'received_at',
        'created_at', 'updated_at',
    ]
    list_per_page = 50
    date_hierarchy = 'received_at'
    ordering = ['-received_at']

    @admin.display(description='Prospect')
    def prospect_link(self, obj):
        if obj.prospect:
            return obj.prospect.business_name
        return format_html('<span style="color:#999">—</span>')

    @admin.display(description='Subject')
    def subject_short(self, obj):
        return obj.subject[:60] + '...' if len(obj.subject) > 60 else obj.subject

    @admin.display(description='Classification')
    def classification_badge(self, obj):
        colours = {
            'interested': '#27ae60', 'not_interested': '#e74c3c',
            'opt_out': '#95a5a6', 'question': '#f39c12',
            'out_of_office': '#3498db', 'bounce': '#c0392b',
            'other': '#7f8c8d',
        }
        colour = colours.get(obj.classification, '#7f8c8d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px">{}</span>',
            colour, obj.get_classification_display()
        )

    @admin.display(description='Needs Reply', boolean=True)
    def needs_reply_badge(self, obj):
        return obj.needs_reply

    @admin.display(description='Replied', boolean=True)
    def replied_badge(self, obj):
        return obj.replied

    @admin.display(description='Auto', boolean=True)
    def auto_replied_badge(self, obj):
        return obj.auto_replied

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReplyTemplate)
class ReplyTemplateAdmin(admin.ModelAdmin):
    list_display = [
        'campaign', 'classification_badge', 'is_active', 'subject_template',
        'updated_at',
    ]
    list_filter = ['campaign', 'classification', 'is_active']
    list_editable = ['is_active']
    search_fields = ['campaign__name', 'subject_template', 'body_html_template']

    fieldsets = (
        (None, {
            'fields': ('campaign', 'classification', 'is_active'),
        }),
        ('Template', {
            'fields': ('subject_template', 'body_html_template'),
            'description': (
                'Available variables: {{FNAME}}, {{COMPANY}}, {{CITY}}, {{SEGMENT}}, '
                '{{ORIGINAL_SUBJECT}}, {{ORIGINAL_BODY_SHORT}}'
            ),
        }),
    )

    @admin.display(description='Classification')
    def classification_badge(self, obj):
        colours = {
            'interested': '#27ae60',
            'question': '#f39c12',
            'other': '#7f8c8d',
        }
        colour = colours.get(obj.classification, '#7f8c8d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px">{}</span>',
            colour, obj.get_classification_display()
        )


@admin.register(MailboxConfig)
class MailboxConfigAdmin(admin.ModelAdmin):
    list_display = [
        'campaign', 'imap_email', 'is_active', 'last_checked_badge', 'last_error_short',
    ]
    list_filter = ['is_active']
    list_select_related = ['campaign']
    readonly_fields = ['last_checked_at', 'last_error']

    fieldsets = (
        (None, {
            'fields': ('campaign', 'is_active'),
        }),
        ('IMAP (Reading Replies)', {
            'fields': ('imap_host', 'imap_port', 'imap_email', 'imap_password'),
        }),
        ('SMTP (Sending Replies)', {
            'fields': ('smtp_host', 'smtp_port', 'smtp_email', 'smtp_password'),
        }),
        ('Status', {
            'fields': ('last_checked_at', 'last_error'),
            'classes': ('collapse',),
        }),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in ('imap_password', 'smtp_password'):
            from django.forms import PasswordInput
            kwargs['widget'] = PasswordInput(render_value=True)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description='Last Checked')
    def last_checked_badge(self, obj):
        if obj.last_checked_at:
            return obj.last_checked_at.strftime('%Y-%m-%d %H:%M')
        return format_html('<span style="color:#999">Never</span>')

    @admin.display(description='Last Error')
    def last_error_short(self, obj):
        if obj.last_error:
            return format_html(
                '<span style="color:#e74c3c">{}</span>',
                obj.last_error[:80]
            )
        return format_html('<span style="color:#27ae60">OK</span>')


@admin.register(Suppression)
class SuppressionAdmin(admin.ModelAdmin):
    list_display = ['email', 'product_scope', 'reason', 'notes', 'created_at']
    list_filter = ['reason', 'product__slug']
    search_fields = ['email', 'notes']

    @admin.display(description='Scope')
    def product_scope(self, obj):
        if obj.product:
            slug = obj.product.slug
            colour = PRODUCT_COLOURS.get(slug, '#95a5a6')
            label = PRODUCT_LABELS.get(slug, slug)
            return format_html(
                '<span style="background:{};color:#fff;padding:3px 8px;border-radius:3px;font-size:11px">{}</span>',
                colour, label
            )
        return format_html('<span style="background:#333;color:#fff;padding:3px 8px;border-radius:3px;font-size:11px">GLOBAL</span>')


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'sequence_number', 'ab_variant', 'sequence_label', 'subject_preview', 'is_active']
    list_filter = ['campaign__product_ref__slug', 'campaign', 'sequence_number', 'ab_variant', 'is_active']
    search_fields = ['subject_template', 'template_name', 'sequence_label']
    ordering = ['campaign', 'sequence_number', 'ab_variant']

    @admin.display(description='Subject')
    def subject_preview(self, obj):
        return obj.subject_template[:80]


@admin.register(CallScript)
class CallScriptAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'segment_display', 'is_active', 'message_preview']
    list_filter = ['campaign__product_ref__slug', 'campaign', 'is_active']

    @admin.display(description='Segment')
    def segment_display(self, obj):
        return obj.segment or 'default'

    @admin.display(description='First Message')
    def message_preview(self, obj):
        return obj.first_message[:100]


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'product', 'feature', 'model', 'version', 'is_active']
    list_filter = ['product__slug', 'feature', 'is_active']
    search_fields = ['name', 'system_prompt']


@admin.register(AIUsageLog)
class AIUsageLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'organization', 'product', 'feature', 'model', 'input_tokens', 'output_tokens', 'cost_usd', 'success']
    list_filter = ['organization', 'product__slug', 'feature', 'model', 'success']
    date_hierarchy = 'created_at'
    readonly_fields = [
        'organization', 'product', 'campaign', 'prospect', 'feature', 'model',
        'input_tokens', 'output_tokens', 'cost_usd', 'latency_ms', 'success',
        'error_message', 'prompt_version', 'created_at',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'source', 'event_type', 'delivery_id_short', 'processed', 'error_short']
    list_filter = ['source', 'event_type', 'processed']
    date_hierarchy = 'created_at'
    readonly_fields = [
        'delivery_id', 'source', 'event_type', 'payload', 'processed',
        'error', 'created_at',
    ]
    search_fields = ['delivery_id', 'event_type']

    def delivery_id_short(self, obj):
        return obj.delivery_id[:12] + '...'
    delivery_id_short.short_description = 'Delivery ID'

    def error_short(self, obj):
        return obj.error[:80] if obj.error else ''
    error_short.short_description = 'Error'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
