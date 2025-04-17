from django.urls import path
from . import views

urlpatterns = [
    path('control.json', views.control_json),
    path('upload-log', views.upload_log),
]
