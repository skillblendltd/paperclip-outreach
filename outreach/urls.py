from django.contrib import admin
from django.urls import path, include

admin.site.site_header = 'Paperclip Outreach'
admin.site.site_title = 'Outreach Admin'
admin.site.index_title = 'Campaign Dashboard'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('campaigns.urls')),
]
