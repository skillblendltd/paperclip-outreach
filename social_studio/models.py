"""
Social Studio models.

Moved from `campaigns` in social-studio-v1 (2026-04-11). The underlying DB
tables (`social_accounts`, `social_posts`, `social_post_deliveries`) keep
their existing names via `Meta.db_table` so the migration is pure ORM-state:
zero data copy, zero downtime.

See docs/social-studio-v1-plan.md for architecture.
"""
from django.db import models

from campaigns.models import BaseModel, Product


class SocialAccount(BaseModel):
    """Social media account credentials per product per platform."""

    PLATFORM_CHOICES = [
        ('linkedin', 'LinkedIn'),
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('twitter', 'Twitter / X'),
        ('google', 'Google Business'),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='social_studio_accounts',
    )
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    account_name = models.CharField(max_length=300, help_text='Display name (e.g. "TaggIQ LinkedIn Page")')
    page_id = models.CharField(max_length=200, blank=True, default='', help_text='Platform page/org ID')
    access_token = models.TextField(blank=True, default='', help_text='OAuth access token')
    refresh_token = models.TextField(blank=True, default='', help_text='OAuth refresh token (if applicable)')
    token_expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'social_accounts'
        unique_together = [('product', 'platform')]
        ordering = ['product', 'platform']

    def __str__(self):
        status = 'ON' if self.is_active else 'OFF'
        return f'{self.account_name} [{self.platform}] - {status}'


class SocialPost(BaseModel):
    """Platform-agnostic social content. Can be cross-posted to multiple accounts.

    v1 adds `headline`, `visual_intent`, `bespoke_html_path`, `media_path` to
    support the HTML + Playwright rendering pipeline.
    """

    VISUAL_INTENT_CHOICES = [
        ('typography_only', 'Text / typography only'),
        ('product_screenshot', 'Product screenshot composite'),
        ('bespoke_html', 'Bespoke HTML authored by designer'),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='social_studio_posts',
    )
    post_number = models.IntegerField(help_text='Sequential number within the content plan')
    headline = models.CharField(
        max_length=280,
        blank=True,
        default='',
        help_text='Short hook used as the visual headline. Separate from body.',
    )
    content = models.TextField(help_text='Post body text (full LinkedIn post text)')
    hashtags = models.CharField(max_length=500, blank=True, default='')
    link_url = models.URLField(blank=True, default='', help_text='URL to include (as first comment on LinkedIn)')

    visual_intent = models.CharField(
        max_length=32,
        choices=VISUAL_INTENT_CHOICES,
        default='bespoke_html',
        help_text='Author-declared rendering strategy',
    )
    bespoke_html_path = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='Relative path to the bespoke HTML file (e.g. rendered_html/post_01.html)',
    )
    media_path = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='Relative path to the rendered PNG (e.g. rendered_images/post_01.png)',
    )

    # Legacy fields kept for compatibility with existing 30 rows
    media_url = models.URLField(blank=True, default='', help_text='[Legacy] Image/video URL')
    media_description = models.CharField(max_length=500, blank=True, default='')
    pillar = models.CharField(max_length=50, blank=True, default='', help_text='Content pillar category')
    scheduled_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'social_posts'
        ordering = ['scheduled_date', 'post_number']
        unique_together = [('product', 'post_number')]

    def __str__(self):
        return f'#{self.post_number} [{self.scheduled_date}] - {self.content[:60]}'


class SocialPostDelivery(BaseModel):
    """Tracks delivery of a post to a specific platform account."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('published', 'Published'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]

    post = models.ForeignKey(
        SocialPost,
        on_delete=models.CASCADE,
        related_name='deliveries',
    )
    account = models.ForeignKey(
        SocialAccount,
        on_delete=models.CASCADE,
        related_name='deliveries',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    platform_post_id = models.CharField(max_length=200, blank=True, default='')
    error = models.TextField(blank=True, default='')
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'social_post_deliveries'
        unique_together = [('post', 'account')]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.account.platform} #{self.post.post_number} [{self.status}]'
