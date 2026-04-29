from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Sum, Count, F, Q
from apps.products.models.products_models import Product, StockBatch, Category, ProductInventory
from django.utils import timezone
from django.contrib import messages

@login_required
def dashboard(request):
    total_products = Product.objects.count()
    # Corrected low stock logic: handle products with inventory and filter by threshold
    low_stock_count = Product.objects.filter(
        Q(stock__lte=F('inventory__low_stock_threshold')) | Q(stock=0)
    ).count()
    
    # Calculate total inventory value
    total_value = Product.objects.aggregate(
        total=Sum(F('stock') * F('unit_price'), output_field=models.DecimalField())
    )['total'] or 0
    
    # Recent items
    recent_products = Product.objects.all().select_related('category', 'inventory')[:5]
    
    # Expiring products (within next 30 days)
    thirty_days_from_now = timezone.now().date() + timezone.timedelta(days=30)
    expiring_soon = Product.objects.filter(
        expiry_date__lte=thirty_days_from_now, 
        expiry_date__gte=timezone.now().date()
    ).count()

    categories = Category.objects.all()

    context = {
        'total_products': total_products,
        'low_stock_count': low_stock_count,
        'total_value': total_value,
        'expiring_soon': expiring_soon,
        'recent_products': recent_products,
        'categories': categories,
    }
    return render(request, 'core/dashboard.html', context)

@login_required
def product_list(request):
    products = Product.objects.all().select_related('category', 'inventory').order_by('-created_at')
    categories = Category.objects.all()
    
    if request.method == 'POST':
        # Simple handler for add/edit if we want to keep it in one view (but separate views are better)
        pass

    return render(request, 'core/product_list.html', {'products': products, 'categories': categories})

@login_required
def product_add(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        category_id = request.POST.get('category')
        unit_price = request.POST.get('unit_price')
        description = request.POST.get('description')
        stock = request.POST.get('stock')
        
        # Expiry related
        production_date = request.POST.get('production_date') or None
        best_before_days = request.POST.get('best_before_days') or None
        expiry_date = request.POST.get('expiry_date') or None
        
        category = get_object_or_404(Category, id=category_id)
        
        product = Product.objects.create(
            name=name,
            category=category,
            unit_price=unit_price,
            description=description,
            stock=stock,
            production_date=production_date,
            best_before_days=best_before_days,
            expiry_date=expiry_date
        )
        # Create inventory record with default threshold
        ProductInventory.objects.create(product=product, low_stock_threshold=10)
        
        messages.success(request, f"Product '{name}' added successfully!")
        return redirect('product_list')
    return redirect('product_list')

@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.name = request.POST.get('name')
        category_id = request.POST.get('category')
        product.unit_price = request.POST.get('unit_price')
        product.description = request.POST.get('description')
        product.stock = request.POST.get('stock')
        
        # Expiry related
        production_date = request.POST.get('production_date') or None
        best_before_days = request.POST.get('best_before_days') or None
        expiry_date = request.POST.get('expiry_date') or None
        
        product.production_date = production_date
        product.best_before_days = best_before_days
        product.expiry_date = expiry_date
        
        if category_id:
            product.category = get_object_or_404(Category, id=category_id)
        
        product.save()
        messages.success(request, f"Product '{product.name}' updated successfully!")
        return redirect('product_list')
    return redirect('product_list')

@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    batches = product.batches.all()
    categories = Category.objects.all()
    return render(request, 'core/product_detail.html', {'product': product, 'batches': batches, 'categories': categories})

@login_required
def category_list(request):
    categories = Category.objects.all().annotate(product_count=Count('products'))
    return render(request, 'core/category_list.html', {'categories': categories})

@login_required
def category_add(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        if name:
            Category.objects.create(name=name, description=description)
            messages.success(request, f"Category '{name}' created successfully!")
        return redirect('category_list')
    return redirect('category_list')

@login_required
def settings_page(request):
    return render(request, 'core/settings.html')
