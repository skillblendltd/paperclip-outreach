"""Admin registration for social_studio models."""
from django.contrib import admin

from .models import SocialAccount, SocialPost, SocialPostDelivery


class SocialPostDeliveryInline(admin.TabularInline):
    model = SocialPostDelivery
    extra = 0
    readonly_fields = ['account', 'status', 'platform_post_id', 'published_at', 'error']


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ['account_name', 'product', 'platform', 'is_active']
    list_filter = ['platform', 'is_active', 'product__slug']


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = [
        'post_number',
        'product',
        'pillar',
        'scheduled_date',
        'visual_intent',
        'media_path_short',
        'delivery_status',
    ]
    list_filter = ['product__slug', 'pillar', 'visual_intent']
    search_fields = ['headline', 'content']
    ordering = ['scheduled_date', 'post_number']
    inlines = [SocialPostDeliveryInline]
    fieldsets = (
        ('Identity', {'fields': ('product', 'post_number', 'pillar', 'scheduled_date')}),
        ('Content', {'fields': ('headline', 'content', 'hashtags', 'link_url')}),
        ('Visual', {'fields': ('visual_intent', 'bespoke_html_path', 'media_path')}),
        ('Legacy', {'fields': ('media_url', 'media_description'), 'classes': ('collapse',)}),
    )

    def media_path_short(self, obj):
        return (obj.media_path or obj.media_url or '—')[:40]
    media_path_short.short_description = 'Media'

    def delivery_status(self, obj):
        deliveries = obj.deliveries.all()
        if not deliveries:
            return '—'
        return ', '.join(f'{d.account.platform}:{d.status}' for d in deliveries)
    delivery_status.short_description = 'Deliveries'


@admin.register(SocialPostDelivery)
class SocialPostDeliveryAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'post', 'account', 'status', 'platform_post_id']
    list_filter = ['status', 'account__platform']
    readonly_fields = ['post', 'account', 'status', 'platform_post_id', 'published_at', 'error']
