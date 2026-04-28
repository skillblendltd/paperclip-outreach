from django.urls import path
from . import views
from . import webhook_handlers

urlpatterns = [
    path('send/', views.outreach_send, name='outreach_send'),
    path('queue/', views.outreach_queue, name='outreach_queue'),
    path('queue/status/', views.outreach_queue_status, name='outreach_queue_status'),
    path('prospects/', views.outreach_prospects, name='outreach_prospects'),
    path('status/', views.outreach_status, name='outreach_status'),
    path('dashboard/', views.outreach_dashboard, name='outreach_dashboard'),
    path('import/', views.outreach_import_prospects, name='outreach_import'),
    # Provider-agnostic call webhook namespace. New canonical path is
    # /api/webhooks/calls/<provider>/. The legacy /api/webhooks/vapi/ is
    # kept as an alias so existing Vapi-side URL config continues to work
    # until you update it in the Vapi dashboard.
    path('webhooks/calls/<str:provider_slug>/', views.call_webhook, name='call_webhook'),
    path('webhooks/vapi/', views.vapi_webhook, name='vapi_webhook'),  # legacy alias
    path('webhooks/taggiq/', webhook_handlers.taggiq_webhook, name='taggiq_webhook'),
    path('calls/', views.outreach_calls, name='outreach_calls'),
    path('calls/stats/', views.outreach_calls_stats, name='outreach_calls_stats'),
    path('script-insights/', views.outreach_script_insights, name='outreach_script_insights'),
    # Sprint 9 — Analytics & Observability
    path('analytics/pipeline/', views.analytics_pipeline, name='analytics_pipeline'),
    path('analytics/funnel/', views.analytics_funnel, name='analytics_funnel'),
    path('analytics/trends/', views.analytics_trends, name='analytics_trends'),
    path('analytics/campaigns/', views.analytics_campaigns, name='analytics_campaigns'),
    path('analytics/actions/', views.analytics_actions, name='analytics_actions'),
    path('health/', views.health_check, name='health_check'),
]
