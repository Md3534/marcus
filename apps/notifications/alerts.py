import logging
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
import requests

from apps.notifications.models import AlertConfiguration, AlertLog, Notification, NotificationChannel, ExpiryMilestone
from apps.products.models import StockBatch
from utils.email import send_resend_email

logger = logging.getLogger(__name__)
User = get_user_model()

def check_and_generate_alerts():
    """
    Scans all active stock batches. For any batch classified as Critical or High risk,
    generates an AlertLog (if not already present) and dispatches alert notifications
    via configured channels (Email, SMS, In-App).
    Also checks for alert escalation rules.
    """
    config = AlertConfiguration.get_solo()
    
    # 1. Fetch active batches with Critical or High risk tiers
    at_risk_batches = StockBatch.objects.filter(
        quantity__gt=0,
        risk_tier__in=['critical', 'high']
    ).select_related('product')
    
    alerts_generated = 0
    alerts_dispatched = 0
    
    for batch in at_risk_batches:
        # Check if an alert log already exists for this batch and risk tier
        existing_alert = AlertLog.objects.filter(
            batch=batch,
            risk_tier=batch.risk_tier,
            status__in=['generated', 'dispatched', 'acknowledged']
        ).first()
        
        if not existing_alert:
            # Create a new alert log
            message = (
                f"Product '{batch.product.name}' (Batch #{batch.batch_number}) is classified as {batch.risk_tier.upper()} risk.\n"
                f"• Expiry Date: {batch.expiry_date}\n"
                f"• Expiry Probability: {batch.risk_probability:.1%}\n"
                f"• Remaining Stock: {batch.quantity} units"
            )
            alert = AlertLog.objects.create(
                batch=batch,
                risk_tier=batch.risk_tier,
                risk_probability=batch.risk_probability,
                message=message,
                status='generated'
            )
            alerts_generated += 1
            
            # Dispatch notifications
            dispatched = dispatch_alert_notifications(alert, config)
            if dispatched:
                alerts_dispatched += 1
                
    # 2. Check escalation rules
    check_and_escalate_alerts(config)
    
    # 3. Check and send expiry milestone emails
    try:
        check_and_send_expiry_milestone_emails()
    except Exception as e:
        logger.error(f"Failed in check_and_send_expiry_milestone_emails: {e}")
    
    return alerts_generated, alerts_dispatched

def dispatch_alert_notifications(alert, config):
    """
    Dispatches notifications for a generated alert to configured recipients
    and all registered users via Resend email, SMS, and in-app channels.
    """
    # Recipients from configuration + registered active users
    config_emails = [e.strip() for e in config.recipient_emails.split(',') if e.strip()]
    user_emails = list(User.objects.filter(is_active=True).exclude(email='').values_list('email', flat=True))
    emails = list(set(config_emails + user_emails))
    
    phones = [p.strip() for p in config.recipient_phones.split(',') if p.strip()]
    
    email_sent = False
    sms_sent = False
    in_app_sent = False
    
    # Send email notification via Resend
    if emails:
        try:
            subject = f"[{alert.risk_tier.upper()} RISK] Expiry Alert for {alert.batch.product.name}"
            html_content = f"""
            <html>
              <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
                  <h2 style="color: #e53e3e; margin-top: 0;">[{alert.risk_tier.upper()} RISK] Product Expiry Warning</h2>
                  <p>Hello,</p>
                  <p>An automated expiry alert has been triggered for a product in your inventory:</p>
                  <div style="background-color: #fff5f5; border-left: 4px solid #e53e3e; padding: 15px; margin: 15px 0;">
                    <p style="margin: 0; font-weight: bold; font-size: 16px; color: #9b2c2c;">{alert.batch.product.name}</p>
                    <p style="margin: 5px 0 0 0; font-size: 14px; color: #4a5568;">Batch Number: <strong>#{alert.batch.batch_number}</strong></p>
                    <p style="margin: 5px 0 0 0; font-size: 14px; color: #4a5568;">Expiry Date: <strong>{alert.batch.expiry_date}</strong></p>
                    <p style="margin: 5px 0 0 0; font-size: 14px; color: #4a5568;">Remaining Stock: <strong>{alert.batch.quantity} units</strong></p>
                    <p style="margin: 5px 0 0 0; font-size: 14px; color: #4a5568;">Risk Tier: <strong style="text-transform: uppercase; color: #e53e3e;">{alert.risk_tier}</strong></p>
                  </div>
                  <p style="font-size: 12px; color: #a0aec0; margin-top: 20px; text-align: center;">Sent via Resend Automated Expiry Alerts &bull; M_D Chippa Inventory</p>
                </div>
              </body>
            </html>
            """
            res = send_resend_email(
                to=emails,
                subject=subject,
                html=html_content,
                text=alert.message
            )
            if res:
                email_sent = True
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            
    # Send SMS notification (simulated via API or logger)
    if phones:
        try:
            logger.info(f"Dispatching SMS to {phones}: {alert.message}")
            sms_sent = True
        except Exception as e:
            logger.error(f"Failed to dispatch SMS alert: {e}")
            
    # Send In-App notification to all registered users
    staff_users = User.objects.filter(is_active=True)

    for u in staff_users:
        try:
            Notification.objects.create(
                user=u,
                title=f"{alert.risk_tier.upper()} Expiry Risk Alert",
                message=alert.message,
                channels="in_app,email"
            )
            in_app_sent = True
        except Exception as e:
            logger.error(f"Failed to create in-app notification for {u.email}: {e}")
            
    # Update status in audit log
    if email_sent or sms_sent or in_app_sent:
        alert.status = 'dispatched'
        alert.dispatched_at = timezone.now()
        alert.save()
        return True
        
    return False

def check_and_escalate_alerts(config):
    """
    Check if any alert has remained unacknowledged longer than escalation_hours.
    If yes, send an escalation email to the escalation contact via Resend.
    """
    cutoff = timezone.now() - timezone.timedelta(hours=config.escalation_hours)
    unacknowledged_alerts = AlertLog.objects.filter(
        status__in=['generated', 'dispatched'],
        created_at__lte=cutoff
    )
    
    for alert in unacknowledged_alerts:
        try:
            subject = f"[ESCALATED - {alert.risk_tier.upper()} RISK] Unresolved Alert: {alert.batch.product.name}"
            escalation_message = (
                f"This is an escalation notice for an unacknowledged expiry risk alert.\n\n"
                f"Alert details:\n{alert.message}\n"
                f"Generated at: {alert.created_at}\n\n"
                f"Please take action immediately."
            )
            html_msg = f"<p>This is an escalation notice for an unacknowledged expiry risk alert.</p><pre>{alert.message}</pre>"
            send_resend_email(
                to=[config.escalation_email],
                subject=subject,
                html=html_msg,
                text=escalation_message
            )
            alert.message += f"\n[Escalated to {config.escalation_email} at {timezone.now()}]"
            alert.save()
        except Exception as e:
            logger.error(f"Failed to escalate alert: {e}")


def check_and_send_expiry_milestone_emails():
    """
    Scans all active stock batches. For any batch that is within one of the milestones
    (7 days, 5 days, 3 days, 1 day before expiry) and has not received
    the email notification for that milestone, dispatches an email notification via Resend
    to all registered users and generates an in-app notification.
    """
    config = AlertConfiguration.get_solo()
    config_emails = [e.strip() for e in config.recipient_emails.split(',') if e.strip()]
    user_emails = list(User.objects.filter(is_active=True).exclude(email='').values_list('email', flat=True))
    emails = list(set(config_emails + user_emails))


    # Get active batches that have an expiry date
    batches = StockBatch.objects.filter(
        quantity__gt=0,
        expiry_date__isnull=False
    ).select_related('product', 'storage_location')

    milestones = [7, 5, 3, 1]
    emails_sent_count = 0
    from django.urls import reverse

    for batch in batches:
        days_to_expiry = (batch.expiry_date - timezone.now().date()).days
        # If already expired, don't send warning milestone emails
        if days_to_expiry < 0:
            continue

        for milestone in milestones:
            # Check if the batch has entered this milestone window (e.g. days_to_expiry <= milestone)
            if days_to_expiry <= milestone:
                # Check if we already sent this milestone email for this batch
                already_sent = ExpiryMilestone.objects.filter(batch=batch, milestone_days=milestone).exists()
                if not already_sent:
                    try:
                        # 1. Send Email Notification if emails are configured
                        if emails:
                            subject = f"M_D Chippa EXPIRY WARNING: {batch.product.name} expires in {days_to_expiry} days!"
                            
                            # Generate HTML content
                            html_content = f"""
                            <html>
                              <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
                                  <h2 style="color: #d4af37; border-bottom: 2px solid #f5f5f5; padding-bottom: 10px;">Expiry Warning Notification</h2>
                                  <p>Hello,</p>
                                  <p>This is an automated notification warning you that a product batch is nearing its expiry date.</p>
                                  
                                  <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                                    <tr style="background: #fafafa;">
                                      <td style="padding: 10px; font-weight: bold; border: 1px solid #eee; width: 150px;">Product:</td>
                                      <td style="padding: 10px; border: 1px solid #eee;">{batch.product.name}</td>
                                    </tr>
                                    <tr>
                                      <td style="padding: 10px; font-weight: bold; border: 1px solid #eee;">Batch Number:</td>
                                      <td style="padding: 10px; border: 1px solid #eee;">{batch.batch_number}</td>
                                    </tr>
                                    <tr style="background: #fafafa;">
                                      <td style="padding: 10px; font-weight: bold; border: 1px solid #eee;">Expiry Date:</td>
                                      <td style="padding: 10px; border: 1px solid #eee; color: #d9534f; font-weight: bold;">{batch.expiry_date}</td>
                                    </tr>
                                    <tr>
                                      <td style="padding: 10px; font-weight: bold; border: 1px solid #eee;">Days Remaining:</td>
                                      <td style="padding: 10px; border: 1px solid #eee; font-weight: bold;">{days_to_expiry} day(s)</td>
                                    </tr>
                                    <tr style="background: #fafafa;">
                                      <td style="padding: 10px; font-weight: bold; border: 1px solid #eee;">Current Stock:</td>
                                      <td style="padding: 10px; border: 1px solid #eee;">{batch.quantity} units</td>
                                    </tr>
                                    <tr>
                                      <td style="padding: 10px; font-weight: bold; border: 1px solid #eee;">Storage Location:</td>
                                      <td style="padding: 10px; border: 1px solid #eee;">{batch.storage_location.name if batch.storage_location else 'Unplaced'}</td>
                                    </tr>
                                  </table>
                                  
                                  <p style="margin-top: 25px;">Please check this batch and take appropriate action (e.g. transfer, discount, or promotion) to avoid inventory loss.</p>
                                  
                                  <div style="margin-top: 30px; text-align: center;">
                                    <a href="http://localhost:8000/products/{batch.product.id}/" 
                                       style="background-color: #d4af37; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                                       View Product Details
                                    </a>
                                  </div>
                                  
                                  <hr style="border: 0; border-top: 1px solid #eee; margin-top: 30px;" />
                                  <p style="font-size: 11px; color: #999; text-align: center;">M_D Chippa Inventory System &bull; Automated Alert Services</p>
                                  </div>
                              </body>
                            </html>
                            """
                            
                            text_content = (
                                f"Expiry Warning: Batch #{batch.batch_number} of '{batch.product.name}' "
                                f"expires in {days_to_expiry} days (on {batch.expiry_date}).\n"
                                f"Current Stock: {batch.quantity} units.\n"
                                f"Storage Location: {batch.storage_location.name if batch.storage_location else 'Unplaced'}."
                            )
                            
                            response = send_resend_email(
                                to=emails,
                                subject=subject,
                                html=html_content,
                                text=text_content
                            )
                            if response:
                                emails_sent_count += 1
                        
                        # 2. Create In-App Notification for all users
                        action_url = reverse('product_detail', args=[batch.product.id])
                        staff_users = User.objects.filter(is_active=True)

                        for u in staff_users:
                            try:
                                Notification.objects.create(
                                    user=u,
                                    title=f"EXPIRY WARNING: {batch.product.name}",
                                    message=(
                                        f"Product '{batch.product.name}' (Batch #{batch.batch_number}) is expiring in {days_to_expiry} days.\n"
                                        f"• Expiry Date: {batch.expiry_date}\n"
                                        f"• Remaining Stock: {batch.quantity} units"
                                    ),
                                    channels="in_app",
                                    action_url=action_url
                                )
                            except Exception as ue:
                                logger.error(f"Failed to create milestone in-app notification for {u.email}: {ue}")
                        
                        # Save record of milestone notification
                        ExpiryMilestone.objects.create(batch=batch, milestone_days=milestone)
                        logger.info(f"Sent milestone {milestone}d expiry alert for batch {batch.batch_number} of {batch.product.name}")
                    except Exception as e:
                        logger.error(f"Failed to send milestone {milestone}d alert for batch {batch.batch_number}: {e}")
                        
    return emails_sent_count
