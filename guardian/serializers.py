# guardian/serializers.py
from rest_framework import serializers
from .models import GuardianControl, GuardianDevice, GuardianLog

class GuardianDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuardianDevice
        fields = ['id', 'token', 'user', 'last_seen']

class GuardianLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuardianLog
        fields = ['timestamp', 'log_text']

class GuardianControlSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuardianControl
        fields = ['id', 'enabled']