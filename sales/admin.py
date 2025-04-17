from django.contrib.auth.models import Group, User
from django.contrib.auth.admin import UserAdmin
from django.contrib import admin

from .models import Item, Sale, StockEntry, Report, SubscriptionPlan, Business
from .forms import CustomUserCreationForm, CustomUserChangeForm
from .utils import assign_user_to_business_group


admin.site.register(Item)
admin.site.register(Sale)
admin.site.register(StockEntry)
admin.site.register(Report)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('subscription_type', 'amount', 'currency', 'frequency')
    search_fields = ('subscription_type',)
    list_filter = ('frequency',)


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('name', 'display_owners', 'subscription_plan', 'subscription_expiry')
    search_fields = ('name', 'owner__username')
    list_filter = ('subscription_plan',)

    def display_owners(self, obj):
        """
        Custom method to display owners in the admin list view.
        """
        return ", ".join([owner.username for owner in obj.owners.all()])
    
    # Set the short description for the admin column
    display_owners.short_description = "Owners"

    def save_model(self, request, obj, form, change):
        """
        Override save_model to assign the owner to the appropriate business group.
        """
        super().save_model(request, obj, form, change)
        for owner in obj.owners.all():  # Assign group for all owners
            assign_user_to_business_group(owner, obj)

class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User
    list_display = ['username', 'email', 'is_staff', 'is_active']
    fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        ('Permissions', {'fields': ('is_staff', 'is_active', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'is_staff', 'is_active'),
        }),
    )

admin.site.unregister(User)  # Unregister default User admin
admin.site.register(User, CustomUserAdmin)  # Register with custom UserAdmin