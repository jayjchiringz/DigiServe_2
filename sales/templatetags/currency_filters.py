#\sales\templatetags\currency_filters.py
from django import template
from sales.utils import format_currency, convert_currency

register = template.Library()

@register.filter(name='currency')
def currency(value, symbol='Ksh '):
    """Format value as currency with 2 decimal places and a currency symbol."""
    return format_currency(value, symbol)

@register.filter
def currency_conversion(amount, currency):
    return convert_currency(amount, 'USD', currency)