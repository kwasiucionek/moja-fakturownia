from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def sum_attribute(queryset, attribute_name):
    """Sumuje wartości określonego atrybutu z listy objektów"""
    total = Decimal('0.00')
    for obj in queryset:
        try:
            value = getattr(obj, attribute_name)
            if value:
                total += Decimal(str(value))
        except (AttributeError, ValueError, TypeError):
            continue
    return total

@register.filter
def div(value, arg):
    """Dzieli wartość przez argument"""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def mul(value, arg):
    """Mnoży wartość przez argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0
