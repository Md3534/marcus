"""
Supply chain models for purchase orders, receiving, and batch management.
Aligns with Walmart-like retail operations.
"""
from django.db import models
from django.utils import timezone
import uuid
from .products_models import Product
from apps.core.models import Business


class Supplier(models.Model):
    """Supplier/Vendor management"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="suppliers")
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    payment_terms = models.CharField(max_length=100, blank=True, help_text="e.g., Net 30, COD")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    """Purchase Order to suppliers"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('confirmed', 'Confirmed'),
        ('partial', 'Partially Received'),
        ('received', 'Fully Received'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="purchase_orders")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, related_name="purchase_orders")
    
    po_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    order_date = models.DateTimeField(default=timezone.now)
    expected_delivery = models.DateField(null=True, blank=True)
    actual_delivery = models.DateField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-order_date']
        indexes = [
            models.Index(fields=['business', '-order_date']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"PO {self.po_number} - {self.supplier.name}"

    @property
    def is_overdue(self):
        if self.expected_delivery and not self.actual_delivery:
            return self.expected_delivery < timezone.now().date()
        return False

    def calculate_total(self):
        """Recalculate total from line items"""
        total = self.items.aggregate(
            total=models.Sum(models.F('quantity') * models.F('unit_price'), 
                           output_field=models.DecimalField())
        )['total'] or 0
        self.total_amount = total
        self.save()


class PurchaseOrderItem(models.Model):
    """Line items for Purchase Orders"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="po_items")
    
    quantity_ordered = models.PositiveIntegerField()
    quantity_received = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['purchase_order', 'product']

    def __str__(self):
        return f"{self.product.name} x {self.quantity_ordered}"

    @property
    def quantity_pending(self):
        return self.quantity_ordered - self.quantity_received

    @property
    def is_fully_received(self):
        return self.quantity_pending == 0


class GoodsReceipt(models.Model):
    """Track receiving of goods from purchase orders"""
    
    RECEIPT_TYPE_CHOICES = [
        ('po', 'Purchase Order'),
        ('return', 'Return'),
        ('adjustment', 'Adjustment'),
        ('transfer', 'Transfer In'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="goods_receipts")
    
    receipt_number = models.CharField(max_length=50, unique=True)
    receipt_type = models.CharField(max_length=20, choices=RECEIPT_TYPE_CHOICES, default='po')
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="receipts")
    
    receipt_date = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-receipt_date']

    def __str__(self):
        return f"GR {self.receipt_number}"


class GoodsReceiptLine(models.Model):
    """Line items for goods receipt - creates batches"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    goods_receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="receipt_lines")
    po_item = models.ForeignKey(PurchaseOrderItem, on_delete=models.SET_NULL, null=True, blank=True)
    
    quantity_received = models.PositiveIntegerField()
    batch_number = models.CharField(max_length=100, blank=True, help_text="Supplier batch/lot number")
    production_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} x {self.quantity_received}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        # Auto-create or update StockBatch when receiving
        if self.batch_number or self.expiry_date:
            from .products_models import StockBatch
            
            batch, created = StockBatch.objects.get_or_create(
                product=self.product,
                batch_number=self.batch_number or f"AUTO-{self.id}",
                defaults={
                    'quantity': self.quantity_received,
                    'initial_quantity': self.quantity_received,
                    'production_date': self.production_date,
                    'expiry_date': self.expiry_date,
                }
            )
            
            if not created:
                # If batch exists, increment quantity
                batch.quantity += self.quantity_received
                batch.initial_quantity += self.quantity_received
                batch.save()
            
            # Update PO item received qty
            if self.po_item:
                self.po_item.quantity_received += self.quantity_received
                self.po_item.save()


class InventoryTransaction(models.Model):
    """
    Audit trail for all inventory movements.
    Enables analytics, variance investigation, and compliance.
    """
    
    TRANSACTION_TYPE_CHOICES = [
        ('received', 'Received'),
        ('sold', 'Sold'),
        ('adjusted', 'Adjusted'),
        ('expired', 'Expired'),
        ('damaged', 'Damaged'),
        ('transferred', 'Transferred'),
        ('returned', 'Returned'),
        ('consumed', 'Consumed (Internal)'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="inventory_transactions")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="transactions")
    batch = models.ForeignKey('products.StockBatch', on_delete=models.SET_NULL, null=True, blank=True)
    
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    quantity_change = models.IntegerField(help_text="Positive for inbound, negative for outbound")
    reference_id = models.CharField(max_length=100, blank=True, help_text="PO/Receipt/Sale number")
    
    notes = models.TextField(blank=True)
    
    created_by = models.CharField(max_length=255, blank=True)  # Can be user or system
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product', '-created_at']),
            models.Index(fields=['business', '-created_at']),
            models.Index(fields=['transaction_type']),
        ]

    def __str__(self):
        return f"{self.transaction_type.upper()} {self.product.name} x {self.quantity_change}"


class StockTransfer(models.Model):
    """
    Transfer inventory between locations/stores (if multi-location).
    Currently single-location, but structure ready for expansion.
    """
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_transit', 'In Transit'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transfer_number = models.CharField(max_length=50, unique=True)
    
    # For future multi-location support
    from_location = models.CharField(max_length=100, default="Main Store")
    to_location = models.CharField(max_length=100, default="Main Store")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    initiated_date = models.DateTimeField(default=timezone.now)
    received_date = models.DateField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transfer {self.transfer_number}"


class StockTransferLine(models.Model):
    """Line items for stock transfers"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    batch = models.ForeignKey('products.StockBatch', on_delete=models.SET_NULL, null=True, blank=True)
    
    quantity_requested = models.PositiveIntegerField()
    quantity_received = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.product.name} x {self.quantity_requested}"
