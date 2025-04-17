from rest_framework import viewsets

from .models import (
    SubscriptionPlan, Business, Item, PriceHistory, Table, Sale,
    StockEntry, Report, DailyReceipt, Category, Expenditure, UserProfile
)

from .serializers import (
    SubscriptionPlanSerializer, BusinessSerializer, ItemSerializer, PriceHistorySerializer, TableSerializer,
    SaleSerializer, StockEntrySerializer, ReportSerializer, DailyReceiptSerializer, CategorySerializer,
    ExpenditureSerializer, UserProfileSerializer
)

class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer


class BusinessViewSet(viewsets.ModelViewSet):
    queryset = Business.objects.all()
    serializer_class = BusinessSerializer


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer


class PriceHistoryViewSet(viewsets.ModelViewSet):
    queryset = PriceHistory.objects.all()
    serializer_class = PriceHistorySerializer


class TableViewSet(viewsets.ModelViewSet):
    queryset = Table.objects.all()
    serializer_class = TableSerializer


class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer


class StockEntryViewSet(viewsets.ModelViewSet):
    queryset = StockEntry.objects.all()
    serializer_class = StockEntrySerializer


class ReportViewSet(viewsets.ModelViewSet):
    queryset = Report.objects.all()
    serializer_class = ReportSerializer


class DailyReceiptViewSet(viewsets.ModelViewSet):
    queryset = DailyReceipt.objects.all()
    serializer_class = DailyReceiptSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ExpenditureViewSet(viewsets.ModelViewSet):
    queryset = Expenditure.objects.all()
    serializer_class = ExpenditureSerializer


class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
