from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import include
from . import views

urlpatterns = [
    path('control.json', views.control_json),
    path('upload-log', views.upload_log),
    path('device-logs', views.get_device_logs),
    path('logs/', views.log_dashboard, name='guardian-log-dashboard'),
    path('control/<str:token>.json', views.device_control_json, name='device_control_json'),
    path('patch/<str:token>', views.get_patch_url, name='get_patch_url'),  # ✅ REQUIRED FOR PATCH
    path('upload-patch/', views.upload_patch_file, name='upload_patch_file')
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
