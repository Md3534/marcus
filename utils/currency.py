"""
Currency Utility Module for Marcus Store / PharmaAudit OS.
Provides standardized Naira currency formatting across views, reports, templates, and notifications.
"""

def format_naira(value, show_symbol=True):
    """
    Format a numeric value into a Naira formatted string.
    Example: 1500.5 -> "₦1,500.50" (or "1,500.50" if show_symbol=False).
    """
    if value is None:
        return "₦0.00" if show_symbol else "0.00"
    try:
        val = float(value)
        formatted = f"{val:,.2f}"
        return f"₦{formatted}" if show_symbol else formatted
    except (ValueError, TypeError):
        return f"₦{value}" if show_symbol else str(value)
