# models.py
from django.db import models
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from django.conf import settings
import uuid

class NotificationChannel(models.TextChoices):
    IN_APP = 'in_app', 'In App'
    EMAIL = 'email', 'Email'
    PUSH = 'push', 'Push Notification'
    SMS = 'sms', 'SMS'


class NotificationTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True)
    subject = models.CharField(max_length=200, blank=True, null=True)
    message = models.TextField()
    html_message = models.TextField(blank=True, null=True)
    channels = models.CharField(max_length=50, default=NotificationChannel.IN_APP)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    template = models.ForeignKey(NotificationTemplate, on_delete=models.CASCADE, null=True, blank=True)
    
    # Core fields
    title = models.CharField(max_length=200)
    message = models.TextField()
    html_message = models.TextField(blank=True, null=True)
    
    # Metadata
    channels = models.CharField(max_length=50, default=NotificationChannel.IN_APP)
    
    # Status tracking
    is_read = models.BooleanField(default=False)
    is_sent = models.BooleanField(default=False)
    
    # Additional data
    action_url = models.URLField(blank=True, null=True)
    category = models.CharField(max_length=50, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', 'created_at']),
            models.Index(fields=['user', 'category']),
            models.Index(fields=['is_sent']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.title}"
    
    def mark_as_read(self):
        self.is_read = True
        self.save()
    
    def mark_as_sent(self):
        self.is_sent = True
        self.sent_at = timezone.now()
        self.save()

class UserNotificationPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preferences')
    email_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    in_app_enabled = models.BooleanField(default=True)
    
    # Category preferences
    preferences = models.JSONField(default=dict, blank=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Preferences for {self.user.email}"


class AlertConfiguration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Thresholds
    critical_threshold_days = models.PositiveIntegerField(default=7, help_text="Expiry within these days is Critical")
    high_threshold_days = models.PositiveIntegerField(default=30, help_text="Expiry within these days is High")
    medium_threshold_days = models.PositiveIntegerField(default=60, help_text="Expiry within these days is Medium")
    
    # Notification recipients
    recipient_emails = models.TextField(default="admin@marcusstore.com", help_text="Comma-separated emails")
    recipient_phones = models.TextField(default="+1234567890", help_text="Comma-separated phone numbers")
    
    # Escalation rules
    escalation_hours = models.PositiveIntegerField(default=24, help_text="Hours before escalation if unacknowledged")
    escalation_email = models.EmailField(default="manager@marcusstore.com", help_text="Escalation email address")
    
    # API Integration settings
    sms_provider_url = models.URLField(default="https://api.sms-gateway.com/send", help_text="SMS gateway API URL")
    sms_api_key = models.CharField(max_length=255, blank=True, null=True, help_text="SMS provider API key")
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'alert_configurations'

    @classmethod
    def get_solo(cls):
        obj, created = cls.objects.get_or_create(id="00000000-0000-0000-0000-000000000001")
        return obj

    def __str__(self):
        return "Alert Configuration"


class AlertLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey("products.StockBatch", on_delete=models.CASCADE, related_name="alerts")
    risk_tier = models.CharField(max_length=20)
    risk_probability = models.FloatField()
    message = models.TextField()
    
    STATUS_CHOICES = [
        ('generated', 'Generated'),
        ('dispatched', 'Dispatched'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='generated')
    
    dispatched_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="acknowledged_alerts")
    
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_alerts")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        db_table = 'alert_logs'

    def __str__(self):
        return f"Alert {self.risk_tier.upper()} - {self.batch.product.name} - Status: {self.status}"


class ExpiryMilestone(models.Model):
    batch = models.ForeignKey("products.StockBatch", on_delete=models.CASCADE, related_name="expiry_milestones")
    milestone_days = models.IntegerField()  # e.g., 30, 14, 7, 5, 3, 1
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('batch', 'milestone_days')
        db_table = 'expiry_milestones'

    def __str__(self):
        return f"Milestone {self.milestone_days}d for {self.batch.product.name} (Batch: {self.batch.batch_number})"