
from django.db import models
import uuid 
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from cloudinary.models import CloudinaryField
from .categories import Category



class Product(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(max_length=255, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products")
    stock = models.PositiveIntegerField(default=0, help_text="Total stock across all batches")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Status
    is_active = models.BooleanField(default=True)
    
    # Summary Inventory Dates (Aggregated from latest/earliest batch)
    production_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True, help_text="Earliest expiry date among active batches")
    best_before_days = models.PositiveIntegerField(null=True, blank=True)
    predicted_expiry_date = models.DateField(null=True, blank=True) # Set by AI
    is_ai_flagged = models.BooleanField(default=False) # AI flags for imminent expiry
    
    def __str__(self):
        return self.name

    @property
    def total_value(self):
        return self.stock * self.unit_price

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category', '-created_at']),
        ]

    @property
    def primary_image_url(self):
        img = self.images.filter(is_primary=True).first()
        return img.image.url if img else ""

    @property
    def is_expired(self):
        from django.utils import timezone
        if self.expiry_date:
            return self.expiry_date < timezone.now().date()
        return False

    def update_stock_from_batches(self):
        """
        Updates product total stock and earliest expiry date from its batches.
        """
        batches = self.batches.filter(quantity__gt=0)
        
        # Calculate total stock
        total_stock = batches.aggregate(models.Sum('quantity'))['quantity__sum'] or 0
        self.stock = total_stock
        
        # Find earliest expiry date (FEFO - First Expired First Out)
        earliest_batch = batches.filter(expiry_date__isnull=False).order_by('expiry_date').first()
        if earliest_batch:
            self.expiry_date = earliest_batch.expiry_date
            self.production_date = earliest_batch.production_date
            
        # Update without recursion
        Product.objects.filter(id=self.id).update(
            stock=self.stock,
            expiry_date=self.expiry_date,
            production_date=self.production_date
        )

    def save(self, *args, **kwargs):
        from datetime import timedelta
        
        # 1. Inherit default best before days from category if not set
        if not self.best_before_days and self.category and self.category.default_best_before_days:
            self.best_before_days = self.category.default_best_before_days

        # 2. Automatically calculate expiry date if production date and best before days are available
        if self.production_date and self.best_before_days and not self.expiry_date:
            self.expiry_date = self.production_date + timedelta(days=self.best_before_days)
        
        self.full_clean() # Ensure validation runs before saving
        super().save(*args, **kwargs)


class StockBatch(models.Model):
    """
    Handles multiple arrivals of the same product with different expiry dates.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="batches")
    batch_number = models.CharField(max_length=100, unique=True)
    quantity = models.PositiveIntegerField(default=0)
    initial_quantity = models.PositiveIntegerField(default=0)
    
    production_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['expiry_date']
        verbose_name_plural = "Stock Batches"

    def __str__(self):
        return f"{self.product.name} - #{self.batch_number} ({self.quantity} units)"

    def is_expired(self):
        from django.utils import timezone
        if self.expiry_date:
            return self.expiry_date < timezone.now().date()
        return False

    def save(self, *args, **kwargs):
        # Auto-calculate expiry if missing but category defaults exist
        if not self.expiry_date and self.production_date and self.product.category.default_best_before_days:
            from datetime import timedelta
            self.expiry_date = self.production_date + timedelta(days=self.product.category.default_best_before_days)
        
        super().save(*args, **kwargs)
        # Update product totals after batch change
        self.product.update_stock_from_batches()


class ProductInventory(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='inventory')
    sku = models.CharField(max_length=100, unique=False, blank=True)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    track_inventory = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Product Inventories"

    @property
    def is_in_stock(self):
        if not self.track_inventory:
            return True
        return self.product.stock > 0

    @property
    def is_low_stock(self):
        if not self.track_inventory:
            return False
        return 0 < self.product.stock <= self.low_stock_threshold

    def __str__(self):
        return f"{self.product.name} - Stock: {self.product.stock}"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = CloudinaryField('image', folder='products/')
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-is_primary', 'created_at']

    def save(self, *args, **kwargs):
        # If this is set as primary, unset all other primary images for this product
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).update(is_primary=False)
        
        # If no primary image exists, make this one primary
        if not ProductImage.objects.filter(product=self.product, is_primary=True).exists():
            self.is_primary = True
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} - Image {self.order}"
