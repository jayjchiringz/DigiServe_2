from django.contrib import admin
from .models import GuardianControl, GuardianDevice, GuardianLog

@admin.register(GuardianDevice)
class GuardianDeviceAdmin(admin.ModelAdmin):
    list_display = ('token', 'user', 'last_seen', 'override_enabled', 'override_value', 'simulate_watu_lock')
    list_editable = ('override_enabled', 'override_value', 'simulate_watu_lock')
    list_filter = ('override_enabled', 'simulate_watu_lock')
    search_fields = ('token',)

admin.site.register(GuardianControl)
admin.site.register(GuardianLog)