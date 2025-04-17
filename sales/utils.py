#/sales/utils.py
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import Group, User
from django.utils.safestring import SafeString
from django.core.exceptions import PermissionDenied

from decimal import Decimal

import requests
import decimal


def assign_user_to_business_group(user, business):
    group, created = Group.objects.get_or_create(name=f"Business-{business.id}")
    user.groups.add(group)


def format_currency(value, currency_symbol='Kshs '):
    """Format value as currency with 2 decimal places and a currency symbol."""
    if isinstance(value, SafeString):
        value = float(str(value))    
    return f"{currency_symbol}{value:,.2f}"


def get_business_for_user(user):
    """
    Retrieves the business associated with a user.
    Handles both owner (OneToOneField) and staff (ManyToManyField).
    """
    if hasattr(user, 'business'):  # Owner
        return user.business
    elif user.businesses.exists():  # Staff
        return user.businesses.first()  # Adjust if multiple businesses are possible
    return None  # No associated business


def convert_currency(amount, from_currency, to_currency):
    api_url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        rates = response.json().get("rates", {})
        rate = rates.get(to_currency)
        if not rate:
            raise ValueError(f"Exchange rate for {to_currency} not found.")
        return Decimal(amount) * Decimal(rate)
    except (requests.RequestException, ValueError) as e:
        print(f"Error fetching exchange rates: {e}")
        return None
        
        
def sanitize_currency(value):
    """
    Convert a currency-formatted string to a Decimal.
    Strips currency symbols, commas, and spaces.
    """
    if value is None:
        return None
    try:
        # Remove non-numeric characters except decimal points
        sanitized_value = value.replace("KSH", "").replace(",", "").strip()
        return decimal.Decimal(sanitized_value)
    except (ValueError, decimal.InvalidOperation):
        raise ValueError(f"Invalid currency value: {value}")


def groups_required(group_names):
    """
    Decorator to restrict view access to users belonging to a specific group.
    """
    def in_groups(user):
        if user.groups.filter(name__in=group_names).exists():
            return True
        raise PermissionDenied  # Raise 403 error if not in the group
    return user_passes_test(in_groups)
