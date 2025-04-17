#\Digiserve\sales\urls.py
from django.conf.urls import handler403
from django.urls import path

from rest_framework.routers import DefaultRouter

from .api import (
    SubscriptionPlanViewSet, BusinessViewSet, ItemViewSet, PriceHistoryViewSet,
    TableViewSet, SaleViewSet, StockEntryViewSet, ReportViewSet, DailyReceiptViewSet,
    CategoryViewSet, ExpenditureViewSet, UserProfileViewSet
)

from .views import (
    sales_list, create_sale, stock_list, add_stock, sales_report, update_price,
    handle_permission_denied, role_based_redirect, financial_summary, pending_sales,
    resume_sale, create_user, manage_users, edit_user, toggle_user_status, assign_role,
    transfer_business, add_business, edit_business, delete_business, business_list,
    activate_business, deactivate_business, delete_item, edit_stock, edit_item,
    SyncView, add_expenditure, expenditure_report, edit_expenditure, delete_expenditure,
)

from . import views  # Import the entire views module

# Create and register API viewsets with the DefaultRouter
router = DefaultRouter()
router.register(r'subscription-plans', SubscriptionPlanViewSet)
router.register(r'businesses', BusinessViewSet)
router.register(r'items', ItemViewSet)
router.register(r'price-histories', PriceHistoryViewSet)
router.register(r'tables', TableViewSet)
router.register(r'sales', SaleViewSet)
router.register(r'stock-entries', StockEntryViewSet)
router.register(r'reports', ReportViewSet)
router.register(r'daily-receipts', DailyReceiptViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'expenditures', ExpenditureViewSet)
router.register(r'user-profiles', UserProfileViewSet)

urlpatterns = [
    path('receipt/<int:receipt_no>/', views.receipt, name='receipt'),
    path('', sales_list, name='sales-list'),                                # Accessed via /sales/
    path('redirect/', role_based_redirect, name='role-based-redirect'),
    path('new/', create_sale, name='create-sale'),                          # Accessed via /sales/new/
    path('stock/', stock_list, name='stock-list'),                          # Accessed via /sales/stock/
    path('stock/add/', add_stock, name='add-stock'),                        # Accessed via /sales/stock/add/
    path('stock/edit/', edit_stock, name='edit-stock'),
    path('edit-item/', edit_item, name='edit-item'),
    path('report/', sales_report, name='sales-report'),                     # Accessed via /sales/report/
    path('update/price/<int:item_id>/', update_price, name='update-price'), # Accessed via /sales/update/price/
    path('delete/item/<int:item_id>/', delete_item, name='delete-item'),
    path('filter-data/', views.filter_data, name='filter-data'),
    path('financial-summary/', financial_summary, name='financial-summary'),

    path('sales/pending/', pending_sales, name='pending-sales'),
    path('sales/resume/<int:receipt_no>/', resume_sale, name='resume-sale'),

    path('create-user/', create_user, name='create-user'),
    path('manage-users/', manage_users, name='manage-users'),
    path('edit-user/<int:user_id>/', edit_user, name='edit-user'),
    path('toggle-user-status/<int:user_id>/', toggle_user_status, name='toggle-user-status'),
    path('manage-users/assign-role/', assign_role, name='assign-role'),
    path('manage-users/transfer-business/', transfer_business, name='transfer-business'),

    path('businesses/', business_list, name='business-list'),
    path('businesses/add/', add_business, name='add-business'),
    path('businesses/<int:business_id>/edit/', edit_business, name='edit-business'),
    path('businesses/<int:business_id>/delete/', delete_business, name='delete-business'),
    path('businesses/<int:business_id>/activate/', activate_business, name='activate-business'),
    path('businesses/<int:business_id>/deactivate/', deactivate_business, name='deactivate-business'),

    path('add-expenditure/', add_expenditure, name='add-expenditure'),  # New path for adding expenditure
    path('expenditure-report/', expenditure_report, name='expenditure-report'),
    path('expenditure/edit/', edit_expenditure, name='edit-expenditure'),
    path('expenditure/delete/<int:expense_id>/', delete_expenditure, name='delete-expenditure'),

    path('api/sync/', SyncView.as_view(), name='sync'),
]

# Append router-generated API routes
urlpatterns += router.urls