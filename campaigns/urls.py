from django.urls import path
from . import views

urlpatterns = [
    path('send/', views.outreach_send, name='outreach_send'),
    path('queue/', views.outreach_queue, name='outreach_queue'),
    path('queue/status/', views.outreach_queue_status, name='outreach_queue_status'),
    path('prospects/', views.outreach_prospects, name='outreach_prospects'),
    path('status/', views.outreach_status, name='outreach_status'),
    path('dashboard/', views.outreach_dashboard, name='outreach_dashboard'),
    path('import/', views.outreach_import_prospects, name='outreach_import'),
    path('webhooks/vapi/', views.vapi_webhook, name='vapi_webhook'),
]
