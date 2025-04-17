from django.urls import path
from . import views

urlpatterns = [
    path('control.json', views.control_json),
    path('upload-log', views.upload_log),
    path('device-logs', views.get_device_logs),
    path('logs/', views.log_dashboard, name='guardian-log-dashboard')
]
