from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Sum, Count, F
from apps.products.models.products_models import Product, StockBatch, Category
from django.utils import timezone

@login_required
def dashboard(request):
    total_products = Product.objects.count()
    low_stock_count = Product.objects.filter(stock__lte=F('inventory__low_stock_threshold')).count()
    
    # Calculate total inventory value
    total_value = Product.objects.aggregate(
        total=Sum(F('stock') * F('unit_price'), output_field=models.DecimalField())
    )['total'] or 0
    
    # Recent items
    recent_products = Product.objects.all()[:5]
    
    # Expiring products (within next 30 days)
    thirty_days_from_now = timezone.now().date() + timezone.timedelta(days=30)
    expiring_soon = Product.objects.filter(
        expiry_date__lte=thirty_days_from_now, 
        expiry_date__gte=timezone.now().date()
    ).count()

    context = {
        'total_products': total_products,
        'low_stock_count': low_stock_count,
        'total_value': total_value,
        'expiring_soon': expiring_soon,
        'recent_products': recent_products,
    }
    return render(request, 'core/dashboard.html', context)

@login_required
def product_list(request):
    products = Product.objects.all().select_related('category', 'inventory')
    return render(request, 'core/product_list.html', {'products': products})

@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    batches = product.batches.all()
    return render(request, 'core/product_detail.html', {'product': product, 'batches': batches})
