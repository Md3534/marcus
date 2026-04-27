# services/notification_service.py
from django.core.mail import send_mail
from django.utils.html import strip_tags
from django.conf import settings
from django.contrib.auth import get_user_model
import logging
from typing import List, Dict, Any
from .models import Notification, NotificationChannel, UserNotificationPreference

logger = logging.getLogger(__name__)
User = get_user_model()


class NotificationService:
    @staticmethod
    def send_notification(
        user: User,
        title: str,
        message: str,
        channels: List[str] = None,
        html_message: str = None,
    ) -> Notification:
        """
        Send a notification to a single user.
        Supports in-app and email channels.
        """
        if channels is None:
            channels = [NotificationChannel.IN_APP]

        # Get or create user preferences
        preferences, _ = UserNotificationPreference.objects.get_or_create(user=user)

        # Filter channels based on preferences
        enabled_channels = [
            channel for channel in channels if getattr(preferences, f"{channel}_enabled", True)
        ]

        if not enabled_channels:
            logger.warning(f"No enabled channels for {user.email}")
            return None

        # Create in-app notification
        notification = Notification.objects.create(
            user=user,
            title=title,
            message=message,
            channels=",".join(enabled_channels),
        )

        # Deliver email if enabled
        if NotificationChannel.EMAIL in enabled_channels:
            NotificationService._send_email(user, title, message, html_message)

        return notification

    @staticmethod
    def send_bulk_notification(
        users: List[User],
        title: str,
        message: str,
        **kwargs,
    ):
        """Send notifications to multiple users"""
        for user in users:
            try:
                NotificationService.send_notification(user, title, message, **kwargs)
            except Exception as e:
                logger.error(f"Failed to send notification to {user.email}: {e}")

    @staticmethod
    def _send_email(user: User, subject: str, message: str, html_message: str = None):
        """Send email notification"""
        plain_message = strip_tags(message)
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message or message,
            fail_silently=True,
        )
