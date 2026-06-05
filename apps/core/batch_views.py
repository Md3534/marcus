"""
Views for batch management, purchase orders, and inventory reports.
Supports Walmart-like retail operations.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, F, Count
from django.utils import timezone
from django.contrib import messages
from datetime import timedelta

from apps.products.models import Product, StockBatch, Supplier, PurchaseOrder, GoodsReceipt, InventoryTransaction


@login_required
def batch_management(request):
    """
    Manage all batches of products with FEFO visibility.
    Show expiry status and allow batch operations.
    """
    # Get all batches ordered by expiry (FEFO)
    batches = StockBatch.objects.select_related('product').order_by('expiry_date')
    
    # Filter options
    filter_status = request.GET.get('status', 'active')
    if filter_status == 'expiring_soon':
        thirty_days = timezone.now().date() + timedelta(days=30)
        batches = batches.filter(
            expiry_date__lte=thirty_days,
            expiry_date__gte=timezone.now().date()
        )
    elif filter_status == 'expired':
        batches = batches.filter(expiry_date__lt=timezone.now().date())
    elif filter_status == 'active':
        batches = batches.filter(expiry_date__gte=timezone.now().date()).filter(quantity__gt=0)
    
    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        batches = batches.filter(
            Q(product__name__icontains=search_query) | 
            Q(batch_number__icontains=search_query)
        )
    
    context = {
        'batches': batches[:100],  # Pagination recommended for production
        'filter_status': filter_status,
        'search_query': search_query,
        'total_batches': StockBatch.objects.count(),
        'expiring_count': StockBatch.objects.filter(
            expiry_date__lte=timezone.now().date() + timedelta(days=30),
            expiry_date__gte=timezone.now().date()
        ).count(),
        'expired_count': StockBatch.objects.filter(
            expiry_date__lt=timezone.now().date()
        ).count(),
    }
    return render(request, 'core/batch_management.html', context)


@login_required
def product_detail_with_batches(request, pk):
    """
    Enhanced product detail showing all batches, stock levels, and batch operations.
    This is the main product detail view for organizing multi-batch scenarios.
    """
    product = get_object_or_404(Product, id=pk)
    batches = product.batches.all().order_by('expiry_date')  # FEFO order
    
    # Analytics
    total_value = sum(batch.quantity * product.unit_price for batch in batches)
    expires_in_days = 999
    if product.expiry_date:
        days_diff = (product.expiry_date - timezone.now().date()).days
        expires_in_days = max(0, days_diff)
    
    # Recent transactions for this product
    recent_transactions = InventoryTransaction.objects.filter(
        product=product
    ).order_by('-created_at')[:10]
    
    context = {
        'product': product,
        'batches': batches,
        'total_value': total_value,
        'expires_in_days': expires_in_days,
        'recent_transactions': recent_transactions,
    }
    return render(request, 'core/product_detail.html', context)


@login_required
def batch_detail(request, batch_id):
    """
    View and manage individual batch.
    Allow adjustments, manual expiry, quarantine, etc.
    """
    batch = get_object_or_404(StockBatch, id=batch_id)
    product = batch.product
    
    # Get all transactions for this batch
    transactions = InventoryTransaction.objects.filter(batch=batch).order_by('-created_at')
    
    context = {
        'batch': batch,
        'product': product,
        'transactions': transactions,
        'is_expired': batch.is_expired(),
    }
    return render(request, 'core/batch_detail.html', context)


@login_required
def purchase_orders_list(request):
    """List all purchase orders with status filters"""
    orders = PurchaseOrder.objects.all().order_by('-order_date')
    
    # Status filter
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        orders = orders.filter(status=status_filter)
    
    # Overdue POs
    overdue_count = sum(1 for o in orders if o.is_overdue)
    
    context = {
        'purchase_orders': orders,
        'status_filter': status_filter,
        'overdue_count': overdue_count,
        'statuses': dict(PurchaseOrder.STATUS_CHOICES),
    }
    return render(request, 'core/purchase_orders.html', context)


@login_required
def expiry_report(request):
    """
    Report on products expiring soon.
    Critical for FEFO and waste reduction (like Walmart's markdown strategy).
    """
    today = timezone.now().date()
    
    # Categorize by expiry urgency
    expired = Product.objects.filter(expiry_date__lt=today)
    
    expiring_7_days = Product.objects.filter(
        expiry_date__gte=today,
        expiry_date__lte=today + timedelta(days=7),
        stock__gt=0
    ).order_by('expiry_date')
    
    expiring_30_days = Product.objects.filter(
        expiry_date__gt=today + timedelta(days=7),
        expiry_date__lte=today + timedelta(days=30),
        stock__gt=0
    ).order_by('expiry_date')
    
    # Calculate potential loss
    expired_value = sum(p.total_value for p in expired)
    expiring_7_value = sum(p.total_value for p in expiring_7_days)
    
    context = {
        'expired': expired,
        'expiring_7_days': expiring_7_days,
        'expiring_30_days': expiring_30_days,
        'expired_value': expired_value,
        'expiring_7_value': expiring_7_value,
        'total_at_risk': expired_value + expiring_7_value,
    }
    return render(request, 'core/expiry_report.html', context)


@login_required
def low_stock_report(request):
    """
    Report products below reorder threshold.
    Useful for automation reordering and supplier management.
    """
    low_stock_products = Product.objects.filter(
        stock__lte=F('inventory__low_stock_threshold')
    ).select_related('category', 'inventory')
    
    # By category
    by_category = {}
    for product in low_stock_products:
        cat_name = product.category.name if product.category else "Uncategorized"
        if cat_name not in by_category:
            by_category[cat_name] = []
        by_category[cat_name].append(product)
    
    context = {
        'low_stock_products': low_stock_products,
        'by_category': by_category,
        'total_units_at_risk': sum(p.stock for p in low_stock_products),
    }
    return render(request, 'core/low_stock_report.html', context)


@login_required
def suppliers_list(request):
    """Manage suppliers"""
    suppliers = Supplier.objects.all().order_by('name')
    
    context = {
        'suppliers': suppliers,
        'total_suppliers': suppliers.count(),
        'active_suppliers': suppliers.filter(is_active=True).count(),
    }
    return render(request, 'core/suppliers.html', context)


@login_required
def stock_transfers_list(request):
    """Manage stock transfers (multi-location support)"""
    from apps.products.models import StockTransfer
    
    transfers = StockTransfer.objects.all().order_by('-initiated_date')
    
    context = {
        'transfers': transfers,
    }
    return render(request, 'core/stock_transfers.html', context)


# AJAX/API Endpoints for batch operations

@login_required
def adjust_batch_quantity(request, batch_id):
    """AJAX endpoint to adjust batch quantity with audit trail"""
    if request.method != 'POST':
        return render(request, '400.html', status=400)
    
    batch = get_object_or_404(StockBatch, id=batch_id)
    old_qty = batch.quantity
    new_qty = int(request.POST.get('quantity', 0))
    reason = request.POST.get('reason', '')
    
    # Log transaction
    qty_change = new_qty - old_qty
    InventoryTransaction.objects.create(
        product=batch.product,
        batch=batch,
        transaction_type='adjusted',
        quantity_change=qty_change,
        reference_id=f"BATCH-{batch_id}",
        notes=reason,
        created_by=str(request.user),
    )
    
    # Update batch
    batch.quantity = new_qty
    batch.save()
    batch.product.update_stock_from_batches()
    
    messages.success(request, f"Batch quantity adjusted from {old_qty} to {new_qty}")
    return redirect('batch_detail', batch_id=batch_id)


@login_required
def mark_batch_expired(request, batch_id):
    """Mark batch as expired and log transaction"""
    if request.method != 'POST':
        return render(request, '400.html', status=400)
    
    batch = get_object_or_404(StockBatch, id=batch_id)
    
    # Log as expired transaction
    InventoryTransaction.objects.create(
        product=batch.product,
        batch=batch,
        transaction_type='expired',
        quantity_change=-batch.quantity,
        reference_id=f"BATCH-{batch_id}",
        notes=f"Batch marked as expired",
        created_by=str(request.user),
    )
    
    # Clear quantity
    batch.quantity = 0
    batch.save()
    batch.product.update_stock_from_batches()
    
    messages.success(request, f"Batch {batch.batch_number} marked as expired")
    return redirect('batch_detail', batch_id=batch_id)
