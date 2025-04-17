#Digiserve\Digiserve\urls.py
from django.contrib.auth.decorators import login_required
from django.views.generic.base import RedirectView
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.contrib import admin
from django.urls import include, path, reverse_lazy
from django.conf import settings

from sales.views import (
    home, profile, add_item, dashboard, role_based_redirect, manage_tables, add_table,
    edit_table, delete_table, manage_users, dashboard1,
)

from sales import views as sales_views

urlpatterns = [
    # Admin route
    path('admin/', admin.site.urls),

    # Sales app routes
    path('sales/', include('sales.urls')),  # Includes all the URLs from the sales app

    # Home route: Redirect to login page
    path('', RedirectView.as_view(url='/accounts/login/')),  # Redirect unauthenticated users to login

    # Redirect route for role-based access
    path('redirect/', role_based_redirect, name='role-based-redirect'),  # Add the redirect route

    # User authentication routes
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('accounts/profile/', profile, name='profile'),  # User profile view
    path('logout/', auth_views.LogoutView.as_view(next_page=reverse_lazy('login')), name='logout'),
    path('password_change/', auth_views.PasswordChangeView.as_view(), name='password_change'),
    path('password_change/done/', auth_views.PasswordChangeDoneView.as_view(), name='password_change_done'),
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    # Dashboard route
    path('dashboard/', login_required(dashboard), name='dashboard'),    
    path('dashboard1/', dashboard1, name='dashboard1'),
    
    # Add item route
    path('add-item/', add_item, name='add-item'),  # Route to add a new item

    # Registration route
    path('register/', sales_views.register, name='register'),  # Route to the registration view
    
    # Manage Tables route
    path('manage-tables/', manage_tables, name='manage-tables'),
    path('manage-tables/add/', add_table, name='add-table'),
    path('manage-tables/<int:pk>/edit/', edit_table, name='edit-table'),
    path('manage-tables/<int:pk>/delete/', delete_table, name='delete-table'),
    
    path('manage-users/', manage_users, name='manage-users'),

    path('', include('guardian.urls'))
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Custom handler for permission denied
handler403 = 'sales.views.handle_permission_denied'

LOGIN_REDIRECT_URL = 'profile'  # Replace with the actual path to your dashboard

if settings.DEBUG:  # Serve media files in development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
