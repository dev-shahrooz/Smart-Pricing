from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def zip_lists(list_a, list_b):
    """Zip two iterables for template consumption."""
    if list_a is None or list_b is None:
        return []
    return zip(list_a, list_b)


@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (TypeError, ValueError):
        return 0.0
