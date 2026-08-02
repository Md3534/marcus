from django import template
from utils.currency import format_naira

register = template.Library()

@register.filter(name='naira')
def naira(value):
    return format_naira(value)
