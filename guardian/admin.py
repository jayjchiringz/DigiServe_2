from django.contrib import admin
from .models import GuardianControl, GuardianLog

admin.site.register(GuardianControl)
admin.site.register(GuardianLog)
