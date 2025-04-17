from django.db import models

class GuardianControl(models.Model):
    enabled = models.BooleanField(default=True)

class GuardianLog(models.Model):
    log_text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
