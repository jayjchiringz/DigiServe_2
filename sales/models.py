from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from django.core.files import File
from django.utils import timezone
from django.db import models, IntegrityError, transaction

from datetime import timedelta
from io import BytesIO

import qrcode


class SubscriptionPlan(models.Model):
    FREQUENCY_CHOICES = [
        ('Daily', 'Daily'),
        ('Monthly', 'Monthly'),
        ('Quarterly', 'Quarterly'),
        ('Yearly', 'Yearly'),
        ('Free', 'Free'),
    ]

    subscription_type = models.CharField(max_length=50, unique=True)  # e.g., Free, Standard, Premium
    description = models.TextField(blank=True)  # Details about the plan
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # Cost of the plan
    currency = models.CharField(max_length=10, default='USD')  # e.g., USD, Ksh
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)  # e.g., Monthly, Yearly

    def __str__(self):
        return f"{self.subscription_type} - {self.frequency} ({self.amount} {self.currency})"


class Business(models.Model):
    CATEGORY_CHOICES = [
        ('bar_restaurant', 'Bar & Restaurant'),
        ('retail_wholesale', 'Retail-Wholesale Shop/Store'),
        ('service', 'Service Industry'),
        ('other', 'Other (Not Listed)'),
    ]

    admin = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='admin_business',
        null=True,
        blank=True
    )    
    name = models.CharField(max_length=200, unique=True)
    subscription_plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.SET_NULL, null=True, related_name='businesses'
    )
    subscription_expiry = models.DateTimeField(null=True, blank=True)
    logo = models.ImageField(upload_to='business_logos/', blank=True, null=True)
    owners = models.ManyToManyField(User, related_name='owned_businesses', blank=True)
    users = models.ManyToManyField(User, related_name='businesses', blank=True)  # Allow multiple users per business
    is_active = models.BooleanField(default=True)  # Business active status
    registration_date = models.DateTimeField(default=now) #, auto_now_add=True)  # Track when the business was registered
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='bar_restaurant'
    )
    
    def save(self, *args, **kwargs):
        if self.subscription_plan:
            frequency = self.subscription_plan.frequency.lower()
            if frequency == 'daily':
                self.subscription_expiry = now() + timedelta(days=1)
            elif frequency == 'monthly':
                self.subscription_expiry = now() + timedelta(days=30)
            elif frequency == 'quarterly':
                self.subscription_expiry = now() + timedelta(days=90)
            elif frequency == 'yearly':
                self.subscription_expiry = now() + timedelta(days=365)
            elif frequency == 'free':
                self.subscription_expiry = now() + timedelta(days=10)                
        
        # Automatically deactivate business if subscription is expired
        if self.subscription_expiry and self.subscription_expiry < timezone.now():
            if self.is_active:
                self.is_active = False
            
        super().save(*args, **kwargs)

    def is_subscription_active(self):
        return self.subscription_expiry and self.subscription_expiry > timezone.now()

    def __str__(self):
        return self.name


class Item(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=200, unique=False)
    package_type = models.CharField(max_length=100)  # e.g., Crate, Box
    units_per_package = models.PositiveIntegerField()  # e.g., 24 bottles per crate
    current_price_per_package = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)  # Unit cost/buying price
    unit_selling_price = models.DecimalField(max_digits=10, decimal_places=2)  # Unit selling price
    stock = models.PositiveIntegerField(default=0)  # Total units in stock
    date_added = models.DateTimeField(auto_now_add=True)  # Field to track when the item is added
    last_stock_update = models.DateTimeField(null=True, blank=True)  # New field for tracking stock updates

    # New field to store an image
    image = models.ImageField(
        upload_to='item_images/', 
        null=True, 
        blank=True, 
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])]
    )
    
    # Audit trail
    last_updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='price_updater'
    )
    last_updated_at = models.DateTimeField(null=True, blank=True)


    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['business', 'name'], name='unique_item_per_business')
        ]

    def save(self, *args, **kwargs):
        if not self.business:
            if self.last_updated_by and hasattr(self.last_updated_by, 'business'):
                self.business = self.last_updated_by.businesses.first()
            else:
                raise ValidationError("Item must be associated with a business.")
        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.name} - {self.package_type}"
        
    def update_stock(self, packages_added, new_price=None, user=None):
        units_added = packages_added * self.units_per_package
        self.stock += units_added
        self.last_stock_update = timezone.now() 

        # Record new price if provided
        if new_price:
            self.current_price_per_package = new_price
            self.last_updated_by = user
            self.last_updated_at = timezone.now()
            PriceHistory.objects.create(item=self, price=new_price, updated_by=user)

        self.save()

    def is_low_stock(self):
        return self.stock < 10  # Example threshold for low stock

    def is_out_of_stock(self):
        return self.stock == 0
        
        
class PriceHistory(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, null=True, blank=True, related_name='price_histories')
    item = models.ForeignKey(Item, related_name='price_histories', on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    date_recorded = models.DateTimeField(default=timezone.now)
    
    # New field to track the user who updated the price
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.business:
            if self.item and self.item.business:
                self.business = self.item.business
            else:
                raise ValidationError("PriceHistory must be linked to a business via an item.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item.name} - {self.price} on {self.date_recorded.strftime('%Y-%m-%d')} by {self.updated_by.username if self.updated_by else 'Unknown'}"


class Table(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, null=True, blank=True, related_name='tables')
    name = models.CharField(max_length=100, unique=False)  # Table name (e.g., Counter1)
    description = models.TextField(blank=True, null=True)  # Optional description
    is_active = models.BooleanField(default=True)  # Status of the table

    class Meta:
        unique_together = ('business', 'name')

    def __str__(self):
        return self.name


class Sale(models.Model):
    PAYMENT_MODES = [
        ('MPesa', 'MPesa'),
        ('Cash', 'Cash'),
        ('Credit/Debit Card', 'Credit/Debit Card'),
    ]
    business = models.ForeignKey(Business, on_delete=models.CASCADE, null=True, blank=True, related_name='sales')
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    tip = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)  # Served by
    customer_name = models.CharField(max_length=100, blank=True, null=True)
    customer_number = models.CharField(max_length=15, blank=True, null=True)
    status = models.CharField(max_length=10, choices=[('Paid', 'Paid'), ('Unpaid', 'Unpaid')], default='Unpaid')
    date_time = models.DateTimeField(auto_now_add=True)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES, default='Cash')
    receipt_no = models.DecimalField(max_digits=20, decimal_places=0)
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    table = models.ForeignKey(Table, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')

    class Meta:        
        pass

    def save(self, *args, **kwargs):
        if not self.business:
            self.business = self.user.business  # Auto-assign the user's business

        if not self.receipt_no:
            today = timezone.now().date()
            daily_receipt, created = DailyReceipt.objects.get_or_create(date=today)
            daily_receipt.last_receipt_no += 1
            daily_receipt.save()
            self.receipt_no = daily_receipt.last_receipt_no

        super().save(*args, **kwargs)
   
    def __str__(self):
        return f"Sale of {self.quantity} x {self.item.name} (Total: {self.total_amount + self.tip})"
    

class StockEntry(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    date_added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Stock entry for {self.item.name} - Quantity: {self.quantity}"


class Report(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, null=True, blank=True, related_name='reports')
    report_name = models.CharField(max_length=100)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.report_name
        

class DailyReceipt(models.Model):
    date = models.DateField(default=timezone.now)  # Tracks the date of the receipt
    last_receipt_no = models.IntegerField(default=0)  # Track the last receipt number for the day
    
    def __str__(self):
        return f"{self.date}: {self.last_receipt_no}"


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
        

class Expenditure(models.Model):
    EXPENSE_TYPE_CHOICES = [
        ('operational', 'Operational Cost'),
        ('fixed', 'Fixed Expense'),
        ('variable', 'Variable Expense'),
        ('capital', 'Capital Expenditure'),
        ('other', 'Other Expenses'),
    ]

    business = models.ForeignKey(
        'Business',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='expenditures'
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(default=timezone.now)
    added_by = models.ForeignKey(User, on_delete=models.CASCADE)
    expense_type = models.CharField(
        max_length=50,
        choices=EXPENSE_TYPE_CHOICES,
        default='operational'
    )

    def __str__(self):
        return f"{self.description} - {self.amount} on {self.date.strftime('%Y-%m-%d')}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    profile_picture = models.ImageField(upload_to='profile_pictures/', default='images/default-profile.png')

    def __str__(self):
        return f"{self.user.username}'s Profile"
