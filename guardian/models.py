from django.db import models
from django.contrib.auth.models import User

class GuardianControl(models.Model):
    device = models.OneToOneField('GuardianDevice', on_delete=models.CASCADE, related_name='control', null=True)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.device.token[:10]}...: {'Enabled' if self.enabled else 'Disabled'}"

class GuardianDevice(models.Model):
    token = models.CharField(max_length=255, unique=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    last_seen = models.DateTimeField(auto_now=True)
    override_enabled = models.BooleanField(default=False)  # ← Add this
    override_value = models.BooleanField(default=True)     # ← Store ON/OFF

    simulate_watu_lock = models.BooleanField(default=False)  # 🔒 New remote simulation flag
    def __str__(self):
        return f"{self.user.username if self.user else 'Unlinked'} - {self.token[:10]}..."

class GuardianLog(models.Model):
    device = models.ForeignKey(GuardianDevice, on_delete=models.CASCADE, related_name='logs', null=True, blank=True)
    log_text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.device.token[:10]} - {self.timestamp.strftime('%H:%M:%S')}"

class GuardianPatch(models.Model):
    device = models.ForeignKey(GuardianDevice, on_delete=models.CASCADE, related_name='patches')
    dex_file = models.FileField(upload_to='patches/')
    version = models.CharField(max_length=32)
    active = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Patch v{self.version} for {self.device.token[:10]}... ({'Active' if self.active else 'Inactive'})"

class GuardianApkUpdate(models.Model):
    apk_file = models.FileField(upload_to='apks/')
    version = models.CharField(max_length=20)
    changelog = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"APK v{self.version} - {'Active' if self.active else 'Inactive'}"
