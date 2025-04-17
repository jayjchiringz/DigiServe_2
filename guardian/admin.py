from django.contrib import admin
from .models import GuardianControl, GuardianDevice, GuardianLog

admin.site.register(GuardianControl)
admin.site.register(GuardianDevice)
admin.site.register(GuardianLog)
