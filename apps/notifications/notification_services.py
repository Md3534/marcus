import logging
import threading
import requests
from django.contrib.contenttypes.models import ContentType
from .models import Notification

import os
from django.conf import settings

logger = logging.getLogger(__name__)

# Credentials & Config (using Django settings as primary source, fallback to environment, and then hardcoded fallback)
QSTACK_NOTIFICATION_API_KEY = getattr(settings, "QSTACK_NOTIFICATION_API_KEY", None) or os.getenv("QSTACK_NOTIFICATION_API_KEY") or "np_4d7078f72d2f00164b1d877079dd3d9d638eff173848397c"
QSTACK_NOTIFICATION_SERVER_URL = getattr(settings, "QSTACK_NOTIFICATION_SERVER_URL", None) or os.getenv("QSTACK_NOTIFICATION_SERVER_URL") or "https://notification.qstack.com.ng/api/v1/notifications/notify"

class NotificationService:
    
    @staticmethod
    def _post_push_request(title, body, payload, channel=None):
        """
        Helper method executed in a background thread to make the HTTP POST call.
        """
        try:
            json_data = {
                "channel": channel or "default",
                "title": title,
                "body": body,
                "payload": payload or {}
            }

            response = requests.post(
                QSTACK_NOTIFICATION_SERVER_URL,
                headers={
                    "X-API-Key": QSTACK_NOTIFICATION_API_KEY,
                    "Content-Type": "application/json"
                },
                json=json_data,
                timeout=10
            )
            response.raise_for_status()
            logger.info("Successfully pushed external notification.")
            return response.json()
        except Exception as e:
            logger.error(f"Failed to send external push: {e}")
            return {"error": str(e)}

    @staticmethod
    def send_external_push(title="System Alert", body="Your invoice has been processed.", payload=None, channel=None):
        """
        Sends an external push notification. Spawns a background thread to make it non-blocking.
        """
        # Spawn a thread to send the HTTP request so it doesn't block Django's response cycle
        thread = threading.Thread(
            target=NotificationService._post_push_request,
            args=(title, body, payload, channel)
        )
        thread.daemon = True
        thread.start()

    @staticmethod
    def send_notification(recipient, actor, title, message, target_obj, category='system_alert', type='info'):
        """
        Sends a single notification to one user, saves it in Django DB, and pushes to socket room.
        """
        if recipient == actor:
            return None 

        # 1. Create the Local Django Notification record
        notification = Notification.objects.create(
            recipient=recipient,
            actor=actor,
            title=title,
            message=message,
            target=target_obj,
            category=category,
            type=type
        )

        # 2. Push to microservice (recipient is dynamic in payload)
        NotificationService.send_external_push(
            title=title,
            body=message,
            payload={
                "notification_id": str(notification.id),
                "category": category,
                "type": type,
                "recipient": recipient.email,
                "actor": actor.email if actor else "System",
            }
        )
        
        return notification

    @staticmethod
    def send_bulk_notification(recipients, actor, title, message, target_obj, category='system_alert'):
        """
        Creates bulk database records and sends push notifications to multiple users.
        """
        valid_recipients = [u for u in recipients if u != actor]
        if not valid_recipients:
            return []

        content_type = ContentType.objects.get_for_model(target_obj) if target_obj else None
        object_id = target_obj.id if target_obj else None
        
        notifications = [
            Notification(
                recipient=user,
                actor=actor,
                title=title,
                message=message,
                content_type=content_type,
                object_id=object_id,
                category=category
            ) for user in valid_recipients
        ]
        
        created_notifications = Notification.objects.bulk_create(notifications)

        # Send push notifications for each recipient asynchronously
        for notification in created_notifications:
            NotificationService.send_external_push(
                title=title,
                body=message,
                payload={
                    "notification_id": str(notification.id),
                    "category": category,
                    "recipient": notification.recipient.email,
                    "actor": actor.email if actor else "System",
                }
            )

        return created_notifications


def dispatch_action_notification_and_email(actor, title, message, target_obj=None, detail_dict=None):
    """
    Sends real-time in-app notification, external push, and email via Resend for user actions (e.g. adding product, category, location, business, batch).
    """
    try:
        from django.contrib.auth import get_user_model
        from utils.email import send_resend_email, DEFAULT_TO_EMAIL
        from .models import AlertConfiguration, Notification

        User = get_user_model()

        # 1. Create In-App notifications for all active staff/admin users
        staff_users = User.objects.filter(is_active=True)
        for u in staff_users:
            try:
                Notification.objects.create(
                    user=u,
                    title=title,
                    message=message,
                    channels="in_app,email"
                )
            except Exception as ue:
                logger.error(f"Error creating in-app notification for {u}: {ue}")

        # 2. Push real-time external push
        NotificationService.send_external_push(
            title=title,
            body=message,
            payload={
                "action": title,
                "actor": actor.email if actor and hasattr(actor, 'email') else "System",
                "details": detail_dict or {}
            }
        )

        # 3. Gather email recipients
        config = AlertConfiguration.get_solo()
        recipients = [e.strip() for e in config.recipient_emails.split(',') if e.strip()]
        if actor and hasattr(actor, 'email') and actor.email and actor.email not in recipients:
            recipients.append(actor.email)
        
        if not recipients:
            recipients = [DEFAULT_TO_EMAIL]

        # 4. Generate clean HTML email
        table_rows_html = ""
        if detail_dict:
            for key, val in detail_dict.items():
                table_rows_html += f"""
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569; width: 140px;">{key}:</td>
                    <td style="padding: 10px; color: #0f172a;">{val}</td>
                </tr>
                """

        html_content = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #0f172a; background-color: #f8fafc; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 28px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
              <div style="background: #0f172a; color: #ffffff; padding: 16px 20px; border-radius: 8px; margin-bottom: 24px;">
                <h2 style="margin: 0; font-size: 18px; font-weight: 700;">{title}</h2>
              </div>
              <p style="font-size: 15px; color: #334155; line-height: 1.5;">{message}</p>
              
              {'<table style="width: 100%; border-collapse: collapse; margin: 20px 0; background: #f8fafc; border-radius: 8px; overflow: hidden;">' + table_rows_html + '</table>' if table_rows_html else ''}
              
              <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #f1f5f9; text-align: center; color: #94a3b8; font-size: 12px;">
                M_D Chippa Inventory OS &bull; Real-time Activity Notification
              </div>
            </div>
          </body>
        </html>
        """

        send_resend_email(
            to=recipients,
            subject=f"[PharmaAudit OS] {title}",
            html=html_content,
            text=message
        )
    except Exception as e:
        logger.error(f"Failed to dispatch action notification and email: {e}")

