from django import template
import locale

register = template.Library()

@register.filter(name='naira')
def naira(value):
    try:
        value = float(value)
        return f"₦{value:,.2f}"
    except (ValueError, TypeError):
        return value
