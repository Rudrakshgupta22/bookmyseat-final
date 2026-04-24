from django import template

register = template.Library()


@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Custom template filter to get dictionary values in templates
    Usage: {{ dict|get_item:key }}
    """
    if dictionary and isinstance(dictionary, dict):
        return dictionary.get(key)
    return None
