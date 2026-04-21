from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_page, name='dashboard_page'),
]
