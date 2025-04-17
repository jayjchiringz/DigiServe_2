# sales/views.py
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from django.contrib.auth import login, authenticate
from django.contrib import messages

from django.core.files.storage import default_storage
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile

from django.db.models.functions import TruncDay, TruncMonth, TruncQuarter, TruncYear, TruncDate
from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Max, Q
from django.utils.timezone import now, timedelta, make_aware
from django.utils import timezone

from django.views.decorators.csrf import csrf_exempt
from django.core.files import File
from django.shortcuts import render, redirect, get_object_or_404
from django.template import RequestContext
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.apps import apps
from django.urls import reverse
from django.db import transaction, IntegrityError

from .payments import initiate_mpesa_payment
from .models import Sale, Item, DailyReceipt, Expenditure, Table, Business, SubscriptionPlan
from .utils import format_currency, assign_user_to_business_group, get_business_for_user, sanitize_currency, groups_required
from .forms import TableForm, BusinessRegistrationForm, UserRegistrationForm, UserProfileForm, PasswordChangeForm, EditUserForm

from .serializers import (
    SubscriptionPlanSerializer, BusinessSerializer, ItemSerializer, PriceHistorySerializer, TableSerializer,
    SaleSerializer, StockEntrySerializer, ReportSerializer, DailyReceiptSerializer, CategorySerializer,
    ExpenditureSerializer, UserProfileSerializer
)

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets, status

from datetime import timedelta, date, datetime
from decimal import Decimal
from pathlib import Path
from io import BytesIO

import requests
import logging
import qrcode
import random
import string
import json
import time

logger = logging.getLogger(__name__)

SERIALIZER_MAPPING = {
    'SubscriptionPlan': SubscriptionPlanSerializer,
    'Business': BusinessSerializer,
    'Item': ItemSerializer,
    'PriceHistory': PriceHistorySerializer,
    'Table': TableSerializer,
    'Sale': SaleSerializer,
    'StockEntry': StockEntrySerializer,
    'Report': ReportSerializer,
    'DailyReceipt': DailyReceiptSerializer,
    'Category': CategorySerializer,
    'Expenditure': ExpenditureSerializer,
    'UserProfile': UserProfileSerializer,
}


def user_has_business_access(user, business):
    """
    Determine if the user has access to the given business.
    """
    return (
        business.is_active and (
            business.users.filter(id=user.id).exists() or
            business.owners.filter(id=user.id).exists()
        )
    )


def register(request):
    businesses = Business.objects.all()  # Query all businesses to populate the dropdown

    if request.method == 'POST':
        user_form = UserRegistrationForm(request.POST)
        business_form = BusinessRegistrationForm(request.POST, request.FILES)

        if user_form.is_valid():
            user = user_form.save(commit=False)
            user.set_password(user_form.cleaned_data['password'])
            user.save()

            selected_business = request.POST.get('business')
            if selected_business == 'add_new' and business_form.is_valid():
                # Create a new business
                business = business_form.save(commit=False)
                business.save()
                business.owners.add(user)

            elif selected_business:
                # Assign user to an existing business
                business = Business.objects.get(id=selected_business)
                assign_user_to_business_group(user, business)

            # Log the user in and redirect
            login(request, user)
            return redirect('dashboard')
    else:
        user_form = UserRegistrationForm()
        business_form = BusinessRegistrationForm()

    return render(request, 'registration/register.html', {
        'user_form': user_form,
        'business_form': business_form,
        'businesses': businesses,  # Pass businesses to the template
    })


MAX_RETRIES = 5
def generate_unique_receipt_no():
    """Generate a unique receipt number using date and a time component."""
    today_str = datetime.now().strftime('%y%j')  # Format as 'y' for year, 'j' for day of year

    for attempt in range(MAX_RETRIES):
        try:
            with transaction.atomic():
                daily_receipt, created = DailyReceipt.objects.select_for_update().get_or_create(date=date.today())

                # Increment last receipt number
                daily_receipt.last_receipt_no = daily_receipt.last_receipt_no + 1 if not created else 1
                daily_receipt.save()

                # Generate receipt number with a timestamp component
                receipt_no = f"{today_str}{daily_receipt.last_receipt_no:04d}{int(time.time() * 1000) % 10000:04d}"

                # Confirm the receipt number doesn’t exist already
                if not Sale.objects.filter(receipt_no=receipt_no).exists():
                    logger.debug(f"Generated unique receipt_no: {receipt_no}")
                    return receipt_no

        except IntegrityError:
            time.sleep(2 ** attempt)  # Retry with exponential backoff

    raise IntegrityError("Failed to generate a unique receipt number after multiple attempts.")


def csrf_failure(request, reason=""):
    return render(request, 'csrf_failure.html', {'reason': reason}, status=403)


@login_required
@groups_required(['Director', 'Client Admin', 'Supervisor'])
def sales_list(request):
    # Get the selected business
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Get date filters from the GET request
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    user_id = request.GET.get('user')

    # Initialize sales queryset filtered by the selected business
    sales = Sale.objects.filter(business=selected_business)

    # Apply date range filters if both start_date and end_date are provided
    if start_date and end_date:
        start_date = make_aware(timezone.datetime.strptime(start_date, '%Y-%m-%dT%H:%M'))
        end_date = make_aware(timezone.datetime.strptime(end_date, '%Y-%m-%dT%H:%M'))
        sales = sales.filter(date_time__range=(start_date, end_date))

    # Filter sales by user if user_id is provided
    if user_id:
        sales = sales.filter(user_id=user_id)

    # Calculate the total sales amount based on filters
    total_sales_amount = sales.aggregate(total_sales=Sum('total_amount'))['total_sales'] or 0

    # Calculate sales summary by user
    sales_summary = sales.values('user__username').annotate(
        units_sold=Sum('quantity'),
        total_sales=Sum('total_amount')
    )

    # Get all users for the filter dropdown, limited to those in the selected business
    users = User.objects.filter(businesses=selected_business)

    return render(request, 'sales/sales_list.html', {
        'sales': sales,
        'sales_summary': sales_summary,
        'users': users,
        'total_sales_amount': total_sales_amount,
    })


def home(request):
    return HttpResponse("<h1>Welcome to DigiServe!</h1>")


@login_required
def dashboard(request):
    print(f"Is user authenticated? {request.user.is_authenticated}")

    # Check if the user is in the "Staff" group but not in the "Client Admin" group
    if request.user.groups.filter(name="Staff").exists() and not request.user.groups.filter(name="Client Admin").exists():
        return redirect('create-sale')

    # Get all businesses managed by the Client Admin
    businesses = Business.objects.filter(owners=request.user)
    subscription_plans = SubscriptionPlan.objects.all()

    if not businesses.exists():
        messages.error(request, "You are not linked to any businesses. Contact your administrator.")
        return redirect('business-list')

    # If multiple businesses exist, show the business list
    if businesses.count() > 1 and 'business_id' not in request.GET:
        return render(request, 'sales/business_list.html', {
            'businesses': businesses,
            'can_manage_businesses': True,  # Add management actions
            'subscription_plans': subscription_plans,
        })

    # Get the selected business or the only available business
    business_id = request.GET.get('business_id')
    if business_id:
        # Validate the selected business and store it in the session
        business = get_object_or_404(businesses, id=business_id)
        request.session['selected_business'] = business.id
    elif 'selected_business' in request.session:
        business = get_object_or_404(businesses, id=request.session['selected_business'])
    else:
        business = businesses.first()
        request.session['selected_business'] = business.id

    # Define date range for the past week
    end_date = timezone.now()
    start_date = end_date - timedelta(days=7)

    # Filter sales data for the user's business within the past week
    sales_data = (
        Sale.objects.filter(business=business, date_time__range=[start_date, end_date])
        .annotate(date=TruncDate('date_time'))
        .values('date')
        .annotate(total_sales=Sum('total_amount'))
        .order_by('date')
    )

    # Extract labels and values for sales
    sales_labels = [str(sale['date']) for sale in sales_data]
    sales_values = [float(sale['total_sales']) for sale in sales_data]

    # Filter stock data for the user's business
    stock_data = (
        Item.objects.filter(business=business)
        .values('name')
        .annotate(total_stock=Sum('stock'))
        .order_by('total_stock')
    )
    stock_labels = [stock['name'] for stock in stock_data]
    stock_values = [int(stock['total_stock']) for stock in stock_data]

    # Generate sales predictions as average of sales
    avg_sales = sum(sales_values) / len(sales_values) if sales_values else 0
    predictions_labels = sales_labels
    predictions_values = [avg_sales] * len(sales_labels)

    # Context for rendering with JSON-encoded lists and strings
    context = {
        'business': business,
        'sales_labels': json.dumps(sales_labels),
        'sales_data': json.dumps(sales_values),
        'stock_labels': json.dumps(stock_labels),
        'stock_data': json.dumps(stock_values),
        'predictions_labels': json.dumps(predictions_labels),
        'predictions_data': json.dumps(predictions_values),
    }

    # Log sales data for debugging
    logger.debug("Aggregated sales_data: %s", sales_data)

    return render(request, 'dashboard.html', context)


@login_required
def dashboard1(request):
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Define date range for the past week
    end_date = timezone.now()
    start_date = end_date - timedelta(days=7)

    # Filter sales data for the user's business within the past week
    sales_data = (
        Sale.objects.filter(business=selected_business, date_time__range=[start_date, end_date])
        .annotate(date=TruncDate('date_time'))
        .values('date')
        .annotate(total_sales=Sum('total_amount'))
        .order_by('date')
    )

    # Extract labels and values for sales
    sales_labels = [str(sale['date']) for sale in sales_data]
    sales_values = [float(sale['total_sales']) for sale in sales_data]

    # Filter stock data for the user's business
    stock_data = (
        Item.objects.filter(business=selected_business)
        .values('name')
        .annotate(total_stock=Sum('stock'))
        .order_by('total_stock')
    )
    stock_labels = [stock['name'] for stock in stock_data]
    stock_values = [int(stock['total_stock']) for stock in stock_data]

    # Generate sales predictions as average of sales
    avg_sales = sum(sales_values) / len(sales_values) if sales_values else 0
    predictions_labels = sales_labels
    predictions_values = [avg_sales] * len(sales_labels)

    # Context for rendering with JSON-encoded lists and strings
    context = {
        'business': selected_business,
        'sales_labels': json.dumps(sales_labels),
        'sales_data': json.dumps(sales_values),
        'stock_labels': json.dumps(stock_labels),
        'stock_data': json.dumps(stock_values),
        'predictions_labels': json.dumps(predictions_labels),
        'predictions_data': json.dumps(predictions_values),
    }

    # Log sales data for debugging
    logger.debug("Aggregated sales_data: %s", sales_data)

    return render(request, 'dashboard.html', context)


# Max retry attempts to prevent infinite loops
MAX_RETRIES = 5
@login_required
def create_sale(request):
    logger.debug("Entered create_sale view.")

    # Determine the selected business
    selected_business = None
    if 'selected_business' in request.session:
        selected_business_id = request.session['selected_business']
        selected_business = Business.objects.filter(id=selected_business_id).first()

    # If no valid business in session, check user access
    if not selected_business or not user_has_business_access(request.user, selected_business):
        user_businesses = Business.objects.filter(users=request.user, is_active=True)
        if user_businesses.exists():
            selected_business = user_businesses.first()  # Default to the first accessible business
            request.session['selected_business'] = selected_business.id
        else:
            messages.error(request, "You are not associated with any active businesses.")
            return redirect('dashboard1')

    items = Item.objects.filter(stock__gt=0, business=selected_business).order_by('name')
    items_with_images = [
        {
            'id': item.id,
            'name': item.name,
            'stock': item.stock,
            'unit_selling_price': item.unit_selling_price,
            'image': item.image.url if item.image and hasattr(item.image, 'url') else '/static/images/no-image.jpg',
        }
        for item in items
    ]
    logger.debug("Items with images: %s", items_with_images)

    tables = Table.objects.filter(is_active=True, business=selected_business).order_by('name')  # Query active tables

    # Step 1: Generate `receipt_no` for display on page load
    if request.method == 'GET':
        try:
            receipt_no = generate_unique_receipt_no()

        except IntegrityError as e:
            receipt_no = None
            logger.error(f"Error during receipt generation: {e}")
            messages.error(request, "Error generating a unique receipt number.")

        except Exception as e:
            logger.exception(f"Unexpected error during receipt number generation: {e}")
            receipt_no = None
            messages.error(request, "An unexpected error occurred. Please contact support.")

        return render(request, 'sales/create_sale.html', {
            'items': items_with_images,
            'receipt_no': receipt_no,
            'tables': tables,
        })

    elif request.method == 'POST':
        # Retrieve receipt_no from the hidden input field
        receipt_no = request.POST.get('receipt_no') or generate_unique_receipt_no()
        tip = float(request.POST.get('tip', 0.00))

        customer_name = request.POST.get('customer_name', '')
        customer_number = request.POST.get('customer_number', '')
        mpesa_number = request.POST.get('mpesa_number', '')
        payment_mode = request.POST.get('payment_mode')

        table_id = request.POST.get('table')
        table = get_object_or_404(Table, id=table_id, business=selected_business) if table_id else None

        status = request.POST.get('status')
        item_ids = request.POST.getlist('items[]')
        quantities = request.POST.getlist('quantities[]')
        prices = request.POST.getlist('prices[]')

        # Filter out any blank item entries to avoid errors
        valid_items = [(item_id, quantity, price) for item_id, quantity, price in zip(item_ids, quantities, prices) if item_id and quantity and price]

        if not valid_items:
            messages.error(request, "Please select an item and provide quantity and price.")
            return render(request, 'sales/create_sale.html', {'items': items, 'receipt_no': receipt_no})

        total_amount = 0
        sales_records = []

        try:
            with transaction.atomic():
                # for item_id, quantity, price in zip(item_ids, quantities, prices):
                for index, (item_id, quantity, price) in enumerate(valid_items):
                    item = Item.objects.select_for_update().get(id=item_id, business=selected_business)
                    quantity = int(quantity)
                    price = float(price)

                    if item.stock < quantity:
                        messages.error(request, f"Cannot sell {quantity} units of {item.name}. Only {item.stock} units in stock.")
                        return render(request, 'sales/create_sale.html', {'items': items, 'receipt_no': receipt_no})

                    item_total = price * quantity
                    total_amount += item_total
                    item.stock -= quantity
                    item.save()

                    sale = Sale(
                        item=item,
                        quantity=quantity,
                        total_amount=item_total,
                        user=request.user,
                        customer_name=customer_name,
                        customer_number=customer_number,
                        status=status,
                        payment_mode=payment_mode,
                        table=table,
                        receipt_no=receipt_no,
                        business=selected_business
                    )

                    # Assign tip only to the first sale record
                    if index == 0:
                        sale.tip = tip
                    sales_records.append(sale)

            for sale in sales_records:
                sale.tip = tip
                sale.save()  # Saves each sale to get a primary key
                logger.info(f"Successfully created sales with receipt_no: {receipt_no}")

            # Step 4: Generate and save QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(f'Receipt No: {receipt_no}')
            qr.make(fit=True)

            img = qr.make_image(fill='black', back_color='white')

            # Define file path
            qr_code_dir = Path(settings.MEDIA_ROOT) / "qr_codes"
            qr_code_dir.mkdir(parents=True, exist_ok=True)  # Ensure the directory exists

            file_path = qr_code_dir / f"receipt_{receipt_no}.png"

            # Save QR code to file
            with file_path.open("wb") as f:
                img.save(f)

            # Update all records with the same QR code path
            qr_code_file_path = f"qr_codes/receipt_{receipt_no}.png"

            print(f"QR Code Path: {qr_code_file_path}")

            # Update all records with the same QR code path
            for sale in sales_records:
                sale.qr_code = qr_code_file_path
            Sale.objects.bulk_update(sales_records, ['qr_code'])

            # Format the total amount for success message
            formatted_total_amount = format_currency(total_amount)

            # Initiate MPesa payment if applicable
            if payment_mode == 'MPesa':
                if not mpesa_number.startswith('254') or len(mpesa_number) != 12:
                    messages.error(request, "Invalid MPesa number. Please enter in the format: 254XXXXXXXXX.")
                    return JsonResponse({'success': False, 'message': "Invalid MPesa number. Please use the format: 254XXXXXXXXX."}, status=400)
                payment_response = initiate_mpesa_payment(mpesa_number, total_amount)
                if 'errorMessage' in payment_response:
                    messages.error(request, payment_response['errorMessage'])
                    return JsonResponse({'success': False, 'message': f"MPesa Payment Error: {error_message}"}, status=400)
                for sale in sales_records:
                    sale.status = 'Paid'
                    sale.save()

                logger.info(f"MPesa payment successful for receipt {receipt_no}. Amount: {total_amount}")

            messages.success(request, f'The Sale of Total: {formatted_total_amount} was successfully submitted as {status} status')
            return JsonResponse({'success': True, 'receipt_no': receipt_no})
        except IntegrityError as e:
            # If IntegrityError happens, log and display the error
            logger.error(f"Integrity error during sale creation: {e}")
            messages.error(request, "There was an error processing the sale. Please try again.")
            return render(request, 'sales/create_sale.html', {
                'items': items,
                'tables': tables,
            })

    # On GET request, generate a unique receipt_no for the page and render it
    else:
        try:
            receipt_no = generate_unique_receipt_no()
            logger.info(f"Successfully generated receipt number: {receipt_no}")
        except IntegrityError as e:
            logger.error(f"Error during receipt generation: {e}")
            receipt_no = None
            messages.error(request, "Error generating a unique receipt number.")
        except Exception as e:
            # Handle unexpected exceptions
            logger.exception(f"Unexpected error during receipt number generation: {e}")
            receipt_no = None
            messages.error(request, "An unexpected error occurred. Please contact support.")

    return render(request, 'sales/create_sale.html', {
        'items': items,
        'receipt_no': receipt_no,
        'tables': tables,  # Pass active tables to the template
    })


def get_timestamp():
    """Returns the current timestamp in the format YYYYMMDDHHMMSS required by the MPesa API."""
    return timezone.now().strftime('%Y%m%d%H%M%S')


@login_required
def stock_list(request):
    # Get the authenticated user's business
    user_business = request.user.business

    # Retrieve search query from GET parameters
    query = request.GET.get('query', '')

    # Base queryset of all items
    items = Item.objects.filter(business=user_business).order_by('-date_added', '-stock')

    if query:
        # Filter items where the name contains the query string (case-insensitive)
        items = items.filter(Q(name__icontains=query))

    # Calculate the number of packages and financial details for each item
    for item in items:
        item.packages = item.stock // item.units_per_package  # Number of full packages
        item.unit_cost = item.current_price_per_package / item.units_per_package
        item.total_cost = item.current_price_per_package * item.packages
        item.total_expected_revenue = item.unit_selling_price * item.packages * item.units_per_package
        item.total_expected_profit_margin = item.total_expected_revenue - item.total_cost

    # Calculate grand totals
    grand_total_cost = sum(item.total_cost for item in items)
    grand_total_expected_revenue = sum(item.total_expected_revenue for item in items)
    grand_total_expected_profit_margin = sum(item.total_expected_profit_margin for item in items)

    context = {
        'items': items,
        'grand_total_cost': grand_total_cost,
        'grand_total_expected_revenue': grand_total_expected_revenue,
        'grand_total_expected_profit_margin': grand_total_expected_profit_margin,
    }

    return render(request, 'sales/stock_list.html', context)


@login_required
def sales_report(request):
    # Determine the timeframe
    timeframe = request.GET.get('timeframe', 'daily')  # Default to daily

    # Set the truncation function based on the selected timeframe
    truncation_mapping = {
        'daily': TruncDay,
        'weekly': TruncDay,  # Django doesn't have a TruncWeek, so we'll use custom logic for weekly
        'monthly': TruncMonth,
        'quarterly': TruncQuarter,
        'annual': TruncYear,
    }

    # Aggregate sales data based on the selected timeframe
    trunc_func = truncation_mapping.get(timeframe, TruncDay)
    sales = Sale.objects.annotate(period=trunc_func('date_time')).values('period').annotate(
        total_sales=Sum('total_amount'),
        total_units=Sum('quantity')
    ).order_by('period')

    total_sales = sales.aggregate(Sum('total_sales'))['total_sales__sum'] or 0

    # Sales by item within the selected period
    sales_by_item = Sale.objects.values('item__name').annotate(total=Sum('quantity')).order_by('-total')

    context = {
        'total_sales': total_sales,
        'sales_by_item': sales_by_item,
        'sales': sales,
        'timeframe': timeframe,
    }

    return render(request, 'sales/sales_report.html', context)


@login_required
def check_stock(request):
    items = Item.objects.all()
    low_stock_items = [item for item in items if item.is_low_stock()]
    out_of_stock_items = [item for item in items if item.is_out_of_stock()]

    return render(request, 'sales/stock_check.html', {
        'low_stock_items': low_stock_items,
        'out_of_stock_items': out_of_stock_items,
    })


@login_required
def add_item(request):
    # Get the selected business from the middleware
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    if request.method == 'POST':
        # Retrieve data from the form
        name = request.POST.get('item_name')
        package_type = request.POST.get('package_type')or request.POST.get('custom_package_type')
        units_per_package = int(request.POST.get('units_per_package', 1))  # Default to 1 if not provided
        current_price_per_package = float(request.POST.get('current_price_per_package'))
        unit_cost = current_price_per_package / units_per_package if units_per_package else 0.0
        unit_selling_price = float(request.POST.get('unit_selling_price', unit_cost * 1.2))  # Default 20% profit margin
        image = request.FILES.get('image', None)  # Handle optional image upload

        # Debug statement
        print(f"Image uploaded: {image}")

        try:
            item = Item.objects.create(
                business=selected_business,
                name=name,
                package_type=package_type,
                units_per_package=units_per_package,
                current_price_per_package=current_price_per_package,
                unit_cost=unit_cost,
                unit_selling_price=unit_selling_price,
                image=image,
            )
            messages.success(request, f"Item '{item.name}' added successfully to {selected_business.name}.")
            return redirect('add-stock')
        except IntegrityError:
            messages.error(request, f"Item '{name}' already exists for {selected_business.name}. Please try another name.")
            return redirect('add-item')

    return render(request, 'sales/add_stock.html', {'business': selected_business})


@login_required
def edit_item(request):
    # Get the selected business from the middleware
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    if request.method == 'POST':
        # Get the item_id from POST data
        item_id = request.POST.get('item_id')
        if not item_id:
            messages.error(request, "No item ID provided.")
            return redirect('add-stock')

        # Fetch the item associated with the given ID and business
        item = get_object_or_404(Item, id=item_id, business=selected_business)

        # Sanitize and update item details
        item.name = request.POST.get('name')
        item.package_type = request.POST.get('package_type')
        item.units_per_package = int(request.POST.get('units_per_package', 0))
        item.current_price_per_package = sanitize_currency(request.POST.get('current_price_per_package'))
        item.unit_selling_price = sanitize_currency(request.POST.get('unit_selling_price'))
        item.stock = int(request.POST.get('stock', 0))

        # Update image if provided
        if 'image' in request.FILES:
            item.image = request.FILES['image']

        # Save the updated item
        item.save()
        messages.success(request, 'Item updated successfully.')
        return redirect('add-stock')

    messages.error(request, "Invalid request method.")
    return redirect('add-stock')


@login_required
def delete_item(request, item_id):
    # Get the business associated with the logged-in user
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Restrict the item to the current user's business
    item = get_object_or_404(Item, id=item_id, business=selected_business)

    # Check if the user has permissions to delete the item
    if not request.user.groups.filter(name__in=['manager', 'admin', 'Client Admin']).exists():
        messages.error(request, "You do not have permission to delete this item.")
        return render(request, 'sales/access_denied.html')

    # Delete the item
    item_name = item.name  # Store the item name for the success message
    item.delete()
    messages.success(request, f"Item '{item_name}' deleted successfully.")
    return redirect('add-stock')


@login_required
@groups_required(['Director', 'Client Admin', 'Supervisor'])
def add_stock(request):
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Fetch items for the selected business
    items = Item.objects.filter(business=selected_business).order_by('name')

    # Log items for debugging
    for item in items:
        print(f"Item: {item.id}, Name: {item.name}, Package Type: {item.package_type}, Stock: {item.stock}")

    if request.method == 'POST':
        item_id = request.POST.get('item')
        packages_added = int(request.POST.get('packages_added', 0))
        updated_price_per_package = request.POST.get('updated_price_per_package', None)
        new_unit_selling_price = request.POST.get('unit_selling_price', None)

        # Validate the selected item
        try:
            item = Item.objects.get(id=item_id, business=selected_business)
        except Item.DoesNotExist:
            messages.error(request, "Selected item does not exist for the current business.")
            return redirect('add-stock')

        # Log selected item for debugging
        print(f"Selected Item: {item.id}, Name: {item.name}, Current Stock: {item.stock}")

        # Update stock and optionally update prices
        if updated_price_per_package:
            updated_price_per_package = float(updated_price_per_package)
            item.update_stock(packages_added, new_price=updated_price_per_package, user=request.user)
        else:
            item.update_stock(packages_added)

        # Update the new unit selling price if provided
        if new_unit_selling_price:
            item.unit_selling_price = float(new_unit_selling_price)
            item.save()

        # Add a success message
        messages.success(request, f"Stock for {item.name} updated successfully!")
        return redirect('add-stock')

    # Render the template
    context = {
        'business': selected_business,
        'items': items,
    }
    return render(request, 'sales/add_stock.html', context)


@login_required
def edit_stock(request):
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    if request.method == 'POST':
        # Log incoming data
        print("POST Data:", request.POST)

        # Get item_id from POST data
        item_id = request.POST.get('item_id')
        item = get_object_or_404(Item, id=item_id, business=selected_business)

        # Extract data from the form
        new_stock = request.POST.get('new_stock')
        new_price_per_package = request.POST.get('new_price_per_package')
        new_unit_selling_price = request.POST.get('new_unit_selling_price')
        package_type = request.POST.get('package_type') or request.POST.get('custom_package_type')
        print(f"Item {item_id} - Package Type Received: {package_type}")

        # Sanitize and update item details
        item.name = request.POST.get('item_name')
        item.units_per_package = int(request.POST.get('units_per_package', 0))

        # Update image if provided
        if 'image' in request.FILES:
            item.image = request.FILES['image']

        # Update stock and prices if provided
        if new_stock:
            item.stock += int(new_stock)
        if new_price_per_package:
            item.current_price_per_package = float(new_price_per_package)
        if new_unit_selling_price:
            item.unit_selling_price = float(new_unit_selling_price)

        # Update package_type if provided
        if package_type:
            item.package_type = package_type

        # Save changes to the database
        item.save()

        messages.success(request, 'Stock updated successfully!')
        return redirect('add-stock')
    else:
        messages.error(request, "Invalid request method.")
        return redirect('add-stock')


# Custom handler for permission denied
def handle_permission_denied(request, exception=None):
    messages.error(request, "Access Denied: You do not have permission to access this page. Please contact the administrator.")
    return redirect('dashboard1')


@login_required
def view_price_history(request, item_id):
    item = Item.objects.get(id=item_id)
    price_histories = item.price_histories.all().order_by('-date_recorded')
    return render(request, 'sales/view_price_history.html', {'item': item, 'price_histories': price_histories})


@login_required
def update_price(request, item_id):
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Restrict the item to the current user's business
    item = get_object_or_404(Item, id=item_id, business=selected_business)

    # Restrict access to managers and admins
    if not request.user.groups.filter(name__in=['manager', 'admin', 'Client Admin']).exists():
        messages.error(request, "You do not have permission to update prices.")
        return render(request, 'sales/access_denied.html')  # Redirect to an access denied page if unauthorized

    # Handle POST request
    if request.method == 'POST':
        new_price = request.POST.get('price')
        if new_price:
            try:
                new_price = float(new_price)  # Convert to float
                if new_price <= 0:
                    raise ValueError("Price must be greater than zero.")  # Prevent invalid values

                item.unit_selling_price = new_price
                item.last_updated_by = request.user
                item.last_updated_at = timezone.now()
                item.save()

                # Add the success message BEFORE redirecting
                messages.success(request, f"Price for '{item.name}' updated successfully.")
                return redirect('update-price', item_id=item_id)

            except ValueError:
                # Handle invalid price input
                return render(request, 'update_price.html', {'item': item, 'error': 'Invalid price entered.'})

    # Render the price update form
    return render(request, 'sales/update_price.html', {'item': item})


@login_required
def receipt(request, receipt_no):
    logger.debug(f"Fetching receipt for receipt_no: {receipt_no}")

    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Fetch all sales for this receipt number
    sales = Sale.objects.filter(receipt_no=receipt_no)
    if not sales.exists():
        logger.error(f"No receipt found for receipt_no: {receipt_no}")
        raise Http404("No such receipt found.")

    # Assume all sales share the same details except for amount and items
    first_sale = sales.first()
    total_amount = sum(sale.total_amount for sale in sales)
    tip = first_sale.tip or 0.00
    business = selected_business

    context = {
        'sales': sales,
        'receipt_no': receipt_no,
        'date_time': first_sale.date_time,
        'customer_name': first_sale.customer_name,
        'customer_number': first_sale.customer_number,
        'status': first_sale.status,
        'total_amount': total_amount,
        'tip': tip,
        'grand_total': total_amount + Decimal(tip or 0),
        'payment_mode': first_sale.payment_mode,
        'served_by': first_sale.user.get_full_name() or first_sale.user.username,
        'business': business
    }

    return render(request, 'sales/receipt.html', context)


def filter_data(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    # Check date parsing
    if start_date and end_date:
        try:
            # Parse dates with timezone awareness
            start_date = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
            end_date = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d'))
            print(f"Filtering sales from {start_date} to {end_date}")

            # Filter and aggregate sales data by date
            sales_data = (
                Sale.objects.filter(date_time__range=(start_date, end_date))
                .annotate(date=TruncDate('date_time'))
                .values('date')
                .annotate(total_sales=Sum('total_amount'))
                .order_by('date')
            )

            # Prepare sales data for JSON response
            sales_labels = [str(sale['date']) for sale in sales_data]
            sales_values = [float(sale['total_sales']) for sale in sales_data]

            # Generate predictions as an average (simple prediction logic)
            avg_sales = sum(sales_values) / len(sales_values) if sales_values else 0
            predictions_data = [avg_sales] * len(sales_labels)

            # Fetch stock data without any filtering
            stock_data = Item.objects.values('name').annotate(total_stock=Sum('stock')).order_by('name')
            stock_labels = [stock['name'] for stock in stock_data]
            stock_values = [int(stock['total_stock']) for stock in stock_data]

            # Return filtered sales and full stock data
            return JsonResponse({
                'sales_labels': sales_labels,
                'sales_data': sales_values,
                'predictions_labels': sales_labels,  # Using sales labels for predictions
                'predictions_data': predictions_data,
                'stock_labels': stock_labels,
                'stock_data': stock_values,
            })

        except Exception as e:
            print(f"Date parsing or data aggregation error: {e}")
            return JsonResponse({'error': 'Error processing the date range or data aggregation.'}, status=400)

    # Return an error if date range is invalid
    return JsonResponse({'error': 'Invalid date range provided.'}, status=400)


@csrf_exempt
def mpesa_callback(request):
    """Handle MPesa callback for payment confirmation."""
    data = request.body.decode('utf-8')
    mpesa_response = json.loads(data)

    receipt_no = mpesa_response['Body']['stkCallback']['CheckoutRequestID']
    result_code = mpesa_response['Body']['stkCallback']['ResultCode']

    if result_code == 0:  # Payment was successful
        Sale.objects.filter(receipt_no=receipt_no).update(status='Paid')
        return JsonResponse({"status": "success"})

    return JsonResponse({"status": "failed"})


@login_required
def role_based_redirect(request):
    if request.user.groups.filter(name="Staff").exists():
        return redirect('create-sale')  # Redirect Staff to the create sale page

    elif request.user.groups.filter(name="Client Admin").exists():
        # Get all businesses linked to the Client Admin
        businesses = Business.objects.filter(owners=request.user)
        subscription_plans = SubscriptionPlan.objects.all()

        # Redirect to the business list page, whether one or multiple businesses exist
        return render(request, 'sales/business_list.html', {
            'businesses': businesses,
            'can_manage_businesses': True,  # Allow management actions
            'subscription_plans': subscription_plans,
        })

    else:
        # Default fallback redirect
        return redirect('dashboard')


@login_required
@groups_required(['Director', 'Client Admin', 'Supervisor'])
def financial_summary(request):
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Current date and time
    today = now()
    end_date = today
    start_date = None

    # Period from query parameters
    period = request.GET.get('period', 'this_month')
    logger.debug(f"Received period: {period}")

    # Define period filters
    if period == 'today':
        # Start and end date are the same for today
        start_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = today.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == 'this_week':
        # Start from the most recent Monday
        start_date = today - timedelta(days=today.weekday())  # Monday of the current week
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        # End date is today (up to now)
        end_date = today.replace(hour=23, minute=59, second=59, microsecond=999999)
        logger.debug(f"This Week: start_date={start_date}, end_date={end_date}")
    elif period == 'this_month':
        start_date = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = today
    elif period == 'this_quarter':
        current_month = today.month
        quarter_start_month = ((current_month - 1) // 3) * 3 + 1
        start_date = today.replace(month=quarter_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = today
    elif period == 'this_mid_year':
        if today.month <= 6:  # First half of the year
            start_date = today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = today.replace(month=6, day=30, hour=23, minute=59, second=59, microsecond=999999)
        else:  # Second half of the year
            start_date = today.replace(month=7, day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = today
    elif period == 'this_year':
        start_date = today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = today
    elif period == 'custom':
        try:
            start_date = datetime.strptime(request.GET.get('start_date'), '%Y-%m-%d')
            end_date = datetime.strptime(request.GET.get('end_date'), '%Y-%m-%d')
        except (TypeError, ValueError):
            logger.error(f"Invalid custom dates: start_date={request.GET.get('start_date')}, end_date={request.GET.get('end_date')}")
            messages.error(request, "Invalid custom date range.")
            return redirect('financial-summary')
    else:
        # Default to the last 30 days if no valid period is provided
        logger.warning(f"Unexpected period value: {period}. Defaulting to last 30 days.")
        start_date = today - timedelta(days=30)
        end_date = today

    # Log the period calculation for debugging
    logger.debug(f"Period: {period}, Start Date: {start_date}, End Date: {end_date}")

    # Revenue from Sales
    total_revenue = Sale.objects.filter(
        date_time__range=(start_date, end_date),
        business=selected_business
    ).aggregate(total_sales=Sum(F('quantity') * F('item__unit_selling_price')))['total_sales'] or Decimal(0)

    # Revenue by payment mode
    mpesa_revenue = Sale.objects.filter(
        date_time__range=(start_date, end_date),
        business=selected_business,
        payment_mode='MPesa'
    ).aggregate(mpesa_total=Sum(F('quantity') * F('item__unit_selling_price')))['mpesa_total'] or Decimal(0)
    cash_revenue = Sale.objects.filter(
        date_time__range=(start_date, end_date),
        business=selected_business,
        payment_mode='Cash'
    ).aggregate(cash_total=Sum(F('quantity') * F('item__unit_selling_price')))['cash_total'] or Decimal(0)
    bank_revenue = Sale.objects.filter(
        date_time__range=(start_date, end_date),
        business=selected_business,
        payment_mode__in=['Credit/Debit Card']
    ).aggregate(bank_total=Sum(F('quantity') * F('item__unit_selling_price')))['bank_total'] or Decimal(0)

    # Paid and Unpaid Bills
    paid_bills = Sale.objects.filter(
        date_time__range=(start_date, end_date),
        business=selected_business,
        status='Paid'
    ).aggregate(total_paid=Sum(F('quantity') * F('item__unit_selling_price')))['total_paid'] or Decimal(0)
    unpaid_bills = Sale.objects.filter(
        date_time__range=(start_date, end_date),
        business=selected_business,
        status='Unpaid'
    ).aggregate(total_unpaid=Sum(F('quantity') * F('item__unit_selling_price')))['total_unpaid'] or Decimal(0)

    # Cost of Goods Sold (COGS)
    total_cogs = Sale.objects.filter(
        date_time__range=(start_date, end_date),
        business=selected_business
    ).aggregate(total_cost=Sum(F('quantity') * F('item__unit_cost')))['total_cost'] or Decimal(0)

    # Expenditure
    expenditures = Expenditure.objects.filter(
        business=selected_business,
        date__range=(start_date, end_date)
    ).order_by('-date')

    total_expenditure = expenditures.aggregate(Sum('amount'))['amount__sum'] or Decimal(0)

    expense_type_choices = dict(Expenditure.EXPENSE_TYPE_CHOICES)

    # Add display name to expense breakdown
    expense_breakdown = expenditures.values('expense_type').annotate(
        total=Sum('amount')
    ).order_by('-total')
    for breakdown in expense_breakdown:
        breakdown['expense_type_display'] = expense_type_choices.get(breakdown['expense_type'], 'Unknown')

    # Gross Profit
    gross_profit = total_revenue - total_cogs

    # Income Before Expenses
    income_before_expenses = total_revenue - total_expenditure

    # Net Profit
    net_profit = gross_profit - total_expenditure

    # Expense type choices
    expense_type_choices = dict(Expenditure.EXPENSE_TYPE_CHOICES)

    context = {
        'total_revenue': total_revenue,
        'mpesa_revenue': mpesa_revenue,
        'cash_revenue': cash_revenue,
        'bank_revenue': bank_revenue,
        'paid_bills': paid_bills,
        'unpaid_bills': unpaid_bills,
        'total_expenditure': total_expenditure,
        'expenditures': expenditures,
        'expense_breakdown': expense_breakdown,
        'expense_type_choices': expense_type_choices,
        'gross_profit': gross_profit,
        'total_cogs': total_cogs,
        'income_before_expenses': income_before_expenses,
        'net_profit': net_profit,
        'period': period,
        'start_date': start_date.strftime('%Y-%m-%d') if start_date else None,
        'end_date': end_date.strftime('%Y-%m-%d') if end_date else None,
        'business': selected_business,
    }
    return render(request, 'sales/financial_summary.html', context)


@login_required
def manage_tables(request):
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Filter tables for the logged-in user's business
    tables = Table.objects.filter(business=selected_business)

    # Debugging: Log the tables for verification
    print(f"Tables for {selected_business}: {tables}")

    # Render the template even if no tables are available
    return render(request, 'sales/manage_tables.html', {'tables': tables})


@login_required
def add_table(request):
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    if request.method == "POST":
        form = TableForm(request.POST)
        if form.is_valid():
            table = form.save(commit=False)
            table.business = selected_business
            form.save()

            messages.success(request, 'Table added successfully!')

            return redirect('manage-tables')
    else:
        form = TableForm()
    return render(request, 'sales/add_table.html', {'form': form})


@login_required
def edit_table(request, pk):
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    table = get_object_or_404(Table, pk=pk, business=selected_business)

    if request.method == "POST":
        form = TableForm(request.POST, instance=table)
        if form.is_valid():
            form.save()
            messages.success(request, f"Table '{table.name}' updated successfully.")
            return redirect('manage-tables')
    else:
        form = TableForm(instance=table)

    return render(request, 'sales/manage_tables.html', {'form': form, 'tables': Table.objects.filter(business=business)})


@login_required
def delete_table(request, pk):
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    table = get_object_or_404(Table, pk=pk, business=selected_business)
    if request.method == "POST":
        table.delete()
        return redirect('manage-tables')
    return render(request, 'sales/confirm_delete.html', {'table': table})


@login_required
def pending_sales(request):
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Query all unpaid sales, grouping by receipt number
    unpaid_sales = Sale.objects.filter(status="Unpaid", business=selected_business).order_by('date_time')

    # Group by receipt_no
    transactions = {}
    for sale in unpaid_sales:
        if sale.receipt_no not in transactions:
            transactions[sale.receipt_no] = {
                'receipt_no': sale.receipt_no,
                'date_time': sale.date_time,
                'customer_name': sale.customer_name,
                'table': sale.table.name if sale.table else "N/A",
                'total_amount': 0,
                'items': []  # To hold individual sale items
            }
        transactions[sale.receipt_no]['total_amount'] += sale.total_amount
        transactions[sale.receipt_no]['items'].append(sale)

    # Convert transactions dictionary into a list for template rendering
    transactions = list(transactions.values())

    return render(request, 'sales/pending_sales.html', {'transactions': transactions})


@login_required
def resume_sale(request, receipt_no):
    logger.debug("Processing resume_sale view.")
    logger.debug(f"Authenticated user: {request.user}, Session key: {request.session.session_key}")

    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Fetch all unpaid sales for the given receipt_no
    sales = Sale.objects.filter(receipt_no=receipt_no, status='Unpaid', business=selected_business)
    if not sales.exists():
        messages.error(request, "No pending sale found for this receipt.")
        return redirect('pending-sales')

    # Fetch shared details (e.g., table, customer name) from the first sale
    sale = sales.first()
    existing_items = sales.select_related('item').all()
    items = Item.objects.filter(stock__gt=0, business=selected_business).order_by('name')  # Fetch available stock items
    items_with_images = [
        {
            'id': item.id,
            'name': item.name,
            'stock': item.stock,
            'unit_selling_price': item.unit_selling_price,
            'image': item.image.url if item.image and hasattr(item.image, 'url') else '/static/images/no-image.jpg',
        }
        for item in items
    ]
    logger.debug("Items with images: %s", items_with_images)

    # Calculate the total for existing items
    existing_total = sum(item.total_amount for item in existing_items)

    if request.method == 'POST':
        # Extract transaction updates
        updated_tip = float(request.POST.get('tip', sale.tip or 0))
        updated_status = request.POST.get('status', sale.status)
        updated_payment_mode = request.POST.get('payment_mode', sale.payment_mode)
        updated_customer_name = request.POST.get('customer_name', sale.customer_name)
        updated_customer_number = request.POST.get('mpesa_number', sale.customer_number)

        # Handle new items added to the sale
        item_ids = request.POST.getlist('items[]')
        quantities = request.POST.getlist('quantities[]')
        prices = request.POST.getlist('prices[]')

        # Filter out empty entries
        new_items = [
            (item_id, quantity, price)
            for item_id, quantity, price in zip(item_ids, quantities, prices)
            if item_id and quantity and price
        ]

        try:
            with transaction.atomic():
                # Update existing sales status and shared details
                for existing_sale in existing_items:
                    existing_sale.status = updated_status
                    existing_sale.payment_mode = updated_payment_mode
                    existing_sale.customer_name = updated_customer_name
                    existing_sale.customer_number = updated_customer_number
                    existing_sale.tip = updated_tip
                    existing_sale.user = request.user
                    existing_sale.save()

                # Process new items if they exist
                if new_items:
                    for item_id, quantity, price in new_items:
                        item = Item.objects.select_for_update().get(id=item_id, business=selected_business)
                        quantity = int(quantity)
                        price = float(price)

                        if item.stock < quantity:
                            messages.error(request, f"Insufficient stock for {item.name}.")
                            raise ValueError(f"Insufficient stock for {item.name}.")

                        # Deduct stock and add new sale items
                        item.stock -= quantity
                        item.save()

                        new_sale = Sale(
                            item=item,
                            quantity=quantity,
                            total_amount=quantity * price,
                            user=request.user,
                            customer_name=updated_customer_name,
                            customer_number=updated_customer_number,
                            status=updated_status,
                            payment_mode=updated_payment_mode,
                            table=sale.table,
                            receipt_no=sale.receipt_no,
                            business=selected_business
                        )
                        new_sale.save()

                # Redirect to receipt if successfu
                logger.info(f"Sale updated successfully for receipt_no: {receipt_no}")
                messages.success(request, "Sale updated successfully!")

                return JsonResponse({
                    'success': True,
                    'receipt_no': receipt_no
                })

        except ValueError as e:
            logger.error(f"Validation error during sale update: {ve}")
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
        except Exception as e:
            logger.error(f"Error updating sale: {e}")
            return JsonResponse({
                'success': False,
                'message': "An unexpected error occurred. Please try again."
            }, status=400)

    # Render the resume sale page with the updated context
    return render(request, 'sales/resume_sale.html', {
        'sale': sale,
        'existing_items': existing_items,
        'items': items_with_images,
        'existing_total': existing_total,  # Pass total to the template
        'tip': sale.tip or 0,
    })


@login_required
def profile(request):
    user = request.user
    if request.method == 'POST':
        profile_form = UserProfileForm(request.POST, instance=user)
        password_form = PasswordChangeForm(request.POST)

        if profile_form.is_valid() and password_form.is_valid():
            # Update user details
            profile_form.save()

            # Change password
            old_password = password_form.cleaned_data.get('old_password')
            if not user.check_password(old_password):
                messages.error(request, "Old password is incorrect.")
            else:
                user.set_password(password_form.cleaned_data.get('new_password'))
                user.save()
                messages.success(request, "Profile updated and password changed successfully.")
                return redirect('login')  # Force re-login after password change
    else:
        profile_form = UserProfileForm(instance=user)
        password_form = PasswordChangeForm()

    return render(request, 'sales/profile.html', {
        'profile_form': profile_form,
        'password_form': password_form,
    })


@login_required
def create_user(request):
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Ensure only Directors and Client Admins can access this view
    if not (request.user.groups.filter(name="Client Admin").exists() or
            request.user.groups.filter(name="Director").exists()):
        messages.error(request, "Access Denied: Only Directors and Client Admins can manage users.")
        return redirect('manage-users')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST, request.FILES, business=selected_business)  # Include request.FILES
        if form.is_valid():
            user = form.save(commit=True)
            staff_group, created = Group.objects.get_or_create(name="Staff")
            user.groups.add(staff_group)
            messages.success(request, f"User '{user.username}' has been created successfully.")
            return redirect('manage-users')  # Redirect back to manage users page
    else:
        form = UserRegistrationForm(business=selected_business)

    # Render the manage_users template with the form context
    users = User.objects.filter(businesses=selected_business)  # Ensure users are passed to the template
    return render(request, 'sales/manage_users.html', {'form': form, 'users': users})


@login_required
@groups_required(['Director', 'Client Admin', 'Supervisor'])
def manage_users(request):
    # Ensure only Directors and Client Admins can access this view
    if not (request.user.groups.filter(name="Client Admin").exists() or
            request.user.groups.filter(name="Director").exists()):
        messages.error(request, "Access Denied: Only Directors and Client Admins can manage users.")
        return redirect('manage-users')

    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    business_users = User.objects.filter(businesses=selected_business)
    all_roles = Group.objects.filter(name__in=["Manager", "Staff", "Supervisor", "Director"])
    owned_businesses = Business.objects.filter(owners=request.user)

    # Initialize the form for creating a new user
    form = UserRegistrationForm(business=selected_business)

    return render(request, 'sales/manage_users.html', {
        'users': business_users,
        'form': form,
        'all_roles': all_roles,
        'owned_businesses': owned_businesses,
    })


@login_required
def edit_user(request, user_id):
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Ensure only Directors and Client Admins can access this view
    if not (request.user.groups.filter(name="Client Admin").exists() or
            request.user.groups.filter(name="Director").exists()):
        messages.error(request, "Access Denied: Only Directors and Client Admins can manage users.")
        return redirect('dashboard')

    user = get_object_or_404(User, id=user_id, businesses=selected_business)

    # Ensure the profile exists for the user
    if not hasattr(user, 'profile'):
        UserProfile.objects.get_or_create(user=user)

    # Fetch all businesses owned by the current admin
    owned_businesses = Business.objects.filter(owners=request.user)

    # Filter roles to only include Manager, Staff, Supervisor, and Director
    all_roles = Group.objects.filter(name__in=["Manager", "Staff", "Supervisor", "Director"])

    if request.method == 'POST':
        form = EditUserForm(request.POST, request.FILES, instance=user)
        #role_ids = request.POST.getlist('roles')
        if form.is_valid():
            profile_picture = form.cleaned_data.get('profile_picture')
            if profile_picture:
                user.profile.profile_picture = profile_picture
                user.profile.save()

            # Update user groups
            selected_roles = request.POST.getlist('roles')  # Get selected role IDs
            user.groups.set(Group.objects.filter(id__in=selected_roles))

            # Handle business transfer
            new_business_id = request.POST.get('business_id')
            if new_business_id:
                new_business = get_object_or_404(Business, id=new_business_id, owners=request.user)

                # Preserve roles by replicating them in the new business
                current_roles = user.groups.all()
                user.businesses.clear()  # Clear current business association
                user.businesses.add(new_business)

                # Assign back the roles
                user.groups.set(current_roles)

            # Update activation status
            is_active = request.POST.get('is_active') == 'on'
            user.is_active = is_active

            form.save()

            messages.success(request, f"User '{user.username}' updated successfully.")
            return redirect('manage-users')
        else:
            print("Form Errors:", form.errors)
            messages.error(request, "There was an error updating the user.")
    else:
        form = EditUserForm(instance=user)

    return render(request, 'sales/manage_users.html', {
        'form': form,
        'user': user,
        'all_roles': all_roles,  # Include all roles
        'owned_businesses': owned_businesses,
    })


@login_required
def assign_role(request):
    if request.method == "POST":
        user_id = request.POST.get('user_id')
        role_id = request.POST.get('role')
        user = get_object_or_404(User, id=user_id)
        role = get_object_or_404(Group, id=role_id)

        # Remove user from all groups and add to the new group
        user.groups.clear()
        user.groups.add(role)
        messages.success(request, f"Role '{role.name}' assigned to {user.username}.")
        return redirect('manage-users')
    else:
        messages.error(request, "Invalid request method.")
        return redirect('manage-users')


@login_required
def transfer_business(request):
    if request.method == "POST":
        user_id = request.POST.get('user_id')
        business_id = request.POST.get('business')
        user = get_object_or_404(User, id=user_id)
        new_business = get_object_or_404(Business, id=business_id, owner=request.user)

        # Assign user to the new business
        user.admin_business = new_business
        user.save()
        messages.success(request, f"{user.username} transferred to business '{new_business.name}'.")
        return redirect('manage-users')
    else:
        messages.error(request, "Invalid request method.")
        return redirect('manage-users')


@login_required
def toggle_user_status(request, user_id):
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Ensure only Directors and Client Admins can access this view
    if not (request.user.groups.filter(name="Client Admin").exists() or
            request.user.groups.filter(name="Director").exists()):
        messages.error(request, "Access Denied: Only Directors and Client Admins can manage users.")
        return redirect('dashboard')

    user = get_object_or_404(User, id=user_id, business=selected_business)

    # Toggle `is_active` status
    user.is_active = not user.is_active
    user.save()

    if user.is_active:
        messages.success(request, f"User '{user.username}' has been activated.")
    else:
        messages.warning(request, f"User '{user.username}' has been deactivated.")

    return redirect('manage-users')


@login_required
@groups_required(['Director', 'Client Admin', 'Supervisor'])
def business_list(request):
    # Fetch businesses owned by the logged-in user
    businesses = Business.objects.filter(owners=request.user)
    subscription_plans = SubscriptionPlan.objects.all()
    can_manage_businesses = request.user.groups.filter(name="Client Admin").exists()

    print("Subscription Plans:", subscription_plans)
    return render(request, 'sales/business_list.html', {
        'businesses': businesses,
        'can_manage_businesses': can_manage_businesses,
        'subscription_plans': subscription_plans,
    })


@login_required
def add_business(request):
    if not request.user.groups.filter(name="Client Admin").exists():
        messages.error(request, "You do not have permission to add a business.")
        return redirect('business-list')  # Redirect to the business list

    if request.method == 'POST':
        form = BusinessRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            business = form.save(commit=False)
            subscription_plan = form.cleaned_data['subscription_plan']

            # Dynamically calculate subscription expiry based on plan frequency
            frequency = subscription_plan.frequency.lower()
            if frequency == 'daily':
                business.subscription_expiry = now() + timedelta(days=1)
            elif frequency == 'monthly':
                business.subscription_expiry = now() + timedelta(days=30)
            elif frequency == 'quarterly':
                business.subscription_expiry = now() + timedelta(days=90)
            elif frequency == 'yearly':
                business.subscription_expiry = now() + timedelta(days=365)
            elif frequency == 'free':
                business.subscription_expiry = now() + timedelta(days=10)

            # Set the default currency to USD if not provided
            currency = request.POST.get('currency', 'USD')

            # Update logo if provided
            if 'logo' in request.FILES:
                business.logo = request.FILES['logo']

            business.save()  # Save the business instance
            business.owners.add(request.user)  # Add the current user as an owner
            messages.success(request, f"Business '{business.name}' has been successfully added.")
            return redirect('business-list')
    else:
        form = BusinessRegistrationForm()

    return render(request, 'sales/business_list.html', {'form': form})


def is_client_admin(user):
    return user.groups.filter(name="Client Admin").exists()

@login_required
@user_passes_test(is_client_admin, login_url='business-list')
def edit_business(request, business_id):
    business = get_object_or_404(Business, id=business_id)

    # Check if the user has the necessary permissions
    if not request.user.groups.filter(name="Client Admin").exists():
        messages.error(request, "You do not have permission to edit this business.")
        return redirect('business-list')

    if request.method == 'POST':
        print("POST Data:", request.POST)  # Log all submitted data

        # Set the default currency to USD if not provided
        currency = request.POST.get('currency', 'USD')

        # Include instance and file data in the form
        form = BusinessRegistrationForm(request.POST, request.FILES, instance=business)
        if form.is_valid():
            # Get the updated business object but don't save yet
            business = form.save(commit=False)

            # Set the default currency
            business.currency = currency

            # Handle recalculation of subscription expiry if the plan changes
            subscription_plan = form.cleaned_data['subscription_plan']
            frequency = subscription_plan.frequency.lower()
            expiry_map = {
                'daily': timedelta(days=1),
                'monthly': timedelta(days=30),
                'quarterly': timedelta(days=90),
                'yearly': timedelta(days=365),
                'free': timedelta(days=10),
            }
            business.subscription_expiry = now() + expiry_map.get(frequency, timedelta(days=0))

            # Update logo if provided
            if 'logo' in request.FILES:
                business.logo = request.FILES['logo']

            # Save the updated business object
            business.save()

            messages.success(request, f"Business '{business.name}' has been successfully updated.")
        else:
            # Log form errors for debugging
            print("Form errors:", form.errors)  # Log errors to console
            messages.error(request, "There was an error updating the business. Please correct the errors below.")

    return redirect('business-list')


@login_required
def activate_business(request, business_id):
    business = get_object_or_404(Business, id=business_id, owners=request.user)
    business.is_active = True
    business.save()
    messages.success(request, f"{business.name} has been activated.")
    return redirect('business-list')


@login_required
def deactivate_business(request, business_id):
    business = get_object_or_404(Business, id=business_id, owners=request.user)
    business.is_active = False
    business.save()
    messages.success(request, f"{business.name} has been deactivated.")
    return redirect('business-list')


@login_required
def delete_business(request, business_id):
    # Logic to delete a business
    pass


class SyncView(APIView):
    def post(self, request):
        model_name = request.data.get('model')  # Expect model name in the payload
        records = request.data.get('records', [])

        # Handle empty records
        if not records:
            return Response({"error": "No records provided"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the model name exists in the mapping
        if model_name not in SERIALIZER_MAPPING:
            return Response(
                {"error": f"Unknown model: {model_name}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Dynamically fetch model and serializer
        serializer_class = SERIALIZER_MAPPING[model_name]
        try:
            model_class = apps.get_model(app_label='sales', model_name=model_name)
        except LookupError:
            return Response(
                {"error": f"Model '{model_name}' not found in app 'sales'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        errors = []
        for record in records:
            serializer = serializer_class(data=record)
            if serializer.is_valid():
                model_class.objects.update_or_create(
                    id=record.get('id'),
                    defaults=serializer.validated_data
                )
            else:
                errors.append(serializer.errors)

        if errors:
            return Response(
                {"error": "Some records failed to sync", "details": errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"message": "Sync successful"}, status=status.HTTP_200_OK)


#@csrf_exempt
def authenticate_user(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')

            user = authenticate(request, username=username, password=password)

            if user is not None:
                # Log the successful authentication
                print(f"User authenticated: {username}")
                return JsonResponse({
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                }, status=200)
            else:
                # Log invalid credentials
                print(f"Invalid credentials for user: {username}")
                return JsonResponse({'error': 'Invalid credentials'}, status=401)
        except Exception as e:
            # Log unexpected errors
            print(f"Error during authentication: {e}")
            return JsonResponse({'error': 'Server error'}, status=500)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
@groups_required(['Director', 'Client Admin', 'Supervisor'])
def expenditure_report(request):
    # Fetch expenditures for the logged-in user's business
    selected_business = getattr(request, 'selected_business', None)
    if not selected_business:
        messages.error(request, "No business selected. Please select a business.")
        return redirect('business-list')

    # Handle filtering by date
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    today = now()  # Current date and time
    if not start_date or not end_date:
        # Default to this month's expenditures
        start_date = today.replace(day=1)  # First day of the month
        end_date = today  # Current day
    else:
        # Ensure start_date and end_date are strings before parsing
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d')

    # Query expenditures within the date range
    expenditures = Expenditure.objects.filter(
        business=selected_business,
        date__range=(start_date, end_date)
    ).order_by('-date')

    # Calculate total expenses
    total_expenditure = expenditures.aggregate(total=Sum('amount'))['total'] or 0

    # Get expense type choices from the model
    expense_type_choices = dict(Expenditure.EXPENSE_TYPE_CHOICES)

    # Render the page
    context = {
        'expenditures': expenditures,
        'total_expenditure': total_expenditure,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'expense_type_choices': expense_type_choices,
    }
    return render(request, 'sales/expenditure_report.html', context)


@login_required
@groups_required(['Director', 'Client Admin', 'Supervisor'])
def add_expenditure(request):
    if request.method == 'POST':
        selected_business = getattr(request, 'selected_business', None)
        if not selected_business:
            messages.error(request, "No business selected.")
            return redirect('business-list')

        # Capture form data
        description = request.POST.get('description')
        amount = request.POST.get('amount')
        expense_type = request.POST.get('expense_type')

        try:
            amount = float(amount)
        except ValueError:
            messages.error(request, "Invalid amount.")
            return redirect('expenditure-report')

        # Save the new expenditure
        Expenditure.objects.create(
            business=selected_business,
            description=description,
            amount=amount,
            expense_type=expense_type,
            added_by=request.user
        )
        messages.success(request, "Expenditure added successfully.")
        return redirect('expenditure-report')

    messages.error(request, "Invalid request method.")
    return redirect('expenditure-report')


@login_required
@groups_required(['Director', 'Client Admin', 'Supervisor'])
def edit_expenditure(request):
    if request.method == 'POST':
        expense_id = request.POST.get('expense_id')
        description = request.POST.get('description')
        amount = request.POST.get('amount')
        expense_type = request.POST.get('expense_type')

        expenditure = get_object_or_404(Expenditure, id=expense_id, business=request.user.businesses.first())
        expenditure.description = description
        expenditure.amount = amount
        expenditure.expense_type = expense_type
        expenditure.save()

        messages.success(request, "Expenditure updated successfully.")
        return redirect('expenditure-report')
    else:
        messages.error(request, "Invalid request method.")
        return redirect('expenditure-report')


@login_required
@groups_required(['Director', 'Client Admin', 'Supervisor'])
def delete_expenditure(request, expense_id):
    expenditure = get_object_or_404(Expenditure, id=expense_id, business=request.user.businesses.first())
    expenditure.delete()
    messages.success(request, "Expenditure deleted successfully.")
    return redirect('expenditure-report')
