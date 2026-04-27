
from django.db import models
import uuid 
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from cloudinary.models import CloudinaryField


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    image = CloudinaryField('image', folder='categories/', blank=True, null=True)
    
    # Expiry settings
    default_best_before_days = models.PositiveIntegerField(
        default=0, 
        help_text="Default number of days before products in this category expire"
    )
    
    EXPIRY_STRATEGY_CHOICES = [
        ('PERISHABLE', 'Perishable (Fresh Foods)'),
        ('STABLE', 'Stable (Canned, Biscuits)'),
        ('MEDICAL', 'Medical (Drugs, Medications)'),
        ('GENERAL', 'General (Non-food items)'),
    ]
    expiry_strategy = models.CharField(
        max_length=20, 
        choices=EXPIRY_STRATEGY_CHOICES, 
        default='GENERAL'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']