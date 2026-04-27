# utils/notification_utils.py
from django.contrib.auth.models import User
from typing import List, Dict, Any, Optional
from ..services.notification_service import NotificationService

def notify_user(
    user: User,
    title: str,
    message: str,
    channels: List[str] = None,
    priority: str = 'medium',
    **kwargs
) -> Optional[Any]:
    """
    Simple function to send notification to a single user
    """
    return NotificationService.send_notification(
        user=user,
        title=title,
        message=message,
        channels=channels,
        priority=priority,
        **kwargs
    )

def notify_users(
    users: List[User],
    title: str,
    message: str,
    channels: List[str] = None,
    priority: str = 'medium',
    **kwargs
) -> List[Any]:
    """
    Simple function to send notification to multiple users
    """
    return NotificationService.send_bulk_notification(
        users=users,
        title=title,
        message=message,
        channels=channels,
        priority=priority,
        **kwargs
    )

# Pre-defined notification types for common use cases
def send_welcome_notification(user: User):
    """Send welcome notification to new user"""
    return notify_user(
        user=user,
        title="Welcome to Our Platform!",
        message=f"Hello {user.username}, welcome to our platform! We're excited to have you.",
        channels=['in_app', 'email'],
        category='welcome'
    )

def send_password_reset_notification(user: User, reset_url: str):
    """Send password reset notification"""
    return notify_user(
        user=user,
        title="Password Reset Request",
        message=f"Click here to reset your password: {reset_url}",
        channels=['email'],
        priority='high',
        category='security',
        action_url=reset_url
    )

def send_order_confirmation(user: User, order_id: str, amount: float):
    """Send order confirmation notification"""
    return notify_user(
        user=user,
        title="Order Confirmed",
        message=f"Your order #{order_id} for ${amount} has been confirmed.",
        channels=['in_app', 'email'],
        category='order',
        extra_data={'order_id': order_id, 'amount': amount}
    )