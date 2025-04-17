from django.db import models
from django.contrib.auth.models import User

class GuardianControl(models.Model):
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"Guardian {'Enabled' if self.enabled else 'Disabled'}"

class GuardianDevice(models.Model):
    token = models.CharField(max_length=255, unique=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username if self.user else 'Unlinked'} - {self.token[:10]}..."

class GuardianLog(models.Model):
    device = models.ForeignKey(GuardianDevice, on_delete=models.CASCADE, related_name='logs')
    log_text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.device.token[:10]} - {self.timestamp.strftime('%H:%M:%S')}"
