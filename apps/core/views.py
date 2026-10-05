import csv
from io import BytesIO
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Sum, Count, F, Q
from django.utils import timezone
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

import uuid
from apps.products.models import Product, StockBatch, Category, ProductInventory, StorageLocation, InventoryTransaction
from apps.notifications.models import AlertConfiguration, AlertLog, Notification
from apps.core.models import Business
from apps.core.batch_views import get_default_business

from utils.currency import format_naira

# Import ML and Alert tasks
from apps.products.ml import run_expiry_predictions_for_all_batches, train_expiry_model
from apps.notifications.alerts import check_and_generate_alerts
from apps.notifications.notification_services import dispatch_action_notification_and_email

# Helpers for Access Control (Role checks bypassed so all registered users can perform all actions)
def check_role(user, allowed_roles=None):
    """Returns True for any authenticated user."""
    return user.is_authenticated


def role_forbidden_response(request, message="You do not have permission to perform this action."):
    messages.error(request, message)
    return redirect('dashboard')


@login_required
def dashboard(request):
    # Run predictions and alert scans in real-time on dashboard view
    try:
        run_expiry_predictions_for_all_batches()
        check_and_generate_alerts()
    except Exception as e:
        # Avoid crashing the dashboard if ML fails
        pass

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

    # Expiry risk distribution counts for Chart.js
    risk_counts = StockBatch.objects.values('risk_tier').annotate(count=Count('id'))
    risk_dist = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
    for r in risk_counts:
        risk_dist[r['risk_tier']] = r['count']

    # Top-at-risk product batches list
    top_at_risk_batches = StockBatch.objects.filter(
        quantity__gt=0
    ).select_related('product', 'storage_location').order_by('-risk_probability', 'expiry_date')[:5]

    categories = Category.objects.all()

    context = {
        'total_products': total_products,
        'low_stock_count': low_stock_count,
        'total_value': total_value,
        'expiring_soon': expiring_soon,
        'recent_products': recent_products,
        'categories': categories,
        'locations': StorageLocation.objects.all().order_by('name'),
        'risk_dist': risk_dist,
        'top_at_risk_batches': top_at_risk_batches,
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def product_list(request):
    from datetime import timedelta
    products = Product.objects.all().select_related('category', 'inventory', 'storage_location').order_by('-created_at')
    categories = Category.objects.all().order_by('name')
    locations = StorageLocation.objects.all().order_by('name')
    
    # Filter & Search parameters
    search_query = request.GET.get('search', '').strip()
    selected_category = request.GET.get('category', '').strip()
    selected_location = request.GET.get('location', '').strip()
    selected_stock_status = request.GET.get('stock_status', '').strip()
    selected_expiry_status = request.GET.get('expiry_status', '').strip()
    
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(inventory__sku__icontains=search_query) |
            Q(category__name__icontains=search_query)
        )
        
    if selected_category:
        products = products.filter(category_id=selected_category)
        
    if selected_location:
        products = products.filter(storage_location_id=selected_location)
        
    if selected_stock_status == 'low_stock':
        products = products.filter(Q(stock__lte=F('inventory__low_stock_threshold')) & Q(stock__gt=0))
    elif selected_stock_status == 'out_of_stock':
        products = products.filter(stock=0)
    elif selected_stock_status == 'in_stock':
        products = products.filter(stock__gt=0)
        
    today = timezone.now().date()
    if selected_expiry_status == 'expired':
        products = products.filter(expiry_date__lt=today)
    elif selected_expiry_status == 'expiring_soon':
        thirty_days = today + timedelta(days=30)
        products = products.filter(expiry_date__gte=today, expiry_date__lte=thirty_days)
    elif selected_expiry_status == 'valid':
        products = products.filter(Q(expiry_date__gt=today + timedelta(days=30)) | Q(expiry_date__isnull=True))

    has_filters = bool(search_query or selected_category or selected_location or selected_stock_status or selected_expiry_status)

    return render(request, 'core/product_list.html', {
        'products': products, 
        'categories': categories, 
        'locations': locations,
        'search_query': search_query,
        'selected_category': selected_category,
        'selected_location': selected_location,
        'selected_stock_status': selected_stock_status,
        'selected_expiry_status': selected_expiry_status,
        'has_filters': has_filters,
    })



@login_required
def product_add(request):
    if not check_role(request.user, ['admin', 'manager', 'staff']):
        return role_forbidden_response(request, "Permission Denied: View-Only users cannot create products.")

    if request.method == 'POST':
        name = request.POST.get('name')
        category_id = request.POST.get('category')
        unit_price = request.POST.get('unit_price')
        description = request.POST.get('description')
        
        stock_raw = request.POST.get('stock')
        try:
            stock = max(0, int(stock_raw)) if stock_raw is not None and str(stock_raw).strip() != '' else 0
        except (ValueError, TypeError):
            stock = 0
        
        # Expiry related
        from datetime import date
        prod_date_raw = request.POST.get('production_date', '').strip()
        production_date = None
        if prod_date_raw:
            try:
                production_date = date.fromisoformat(prod_date_raw)
            except (ValueError, TypeError):
                production_date = None

        best_before_days_raw = request.POST.get('best_before_days')
        try:
            best_before_days = int(best_before_days_raw) if best_before_days_raw and str(best_before_days_raw).strip().isdigit() else None
        except (ValueError, TypeError):
            best_before_days = None

        exp_date_raw = request.POST.get('expiry_date', '').strip()
        expiry_date = None
        if exp_date_raw:
            try:
                expiry_date = date.fromisoformat(exp_date_raw)
            except (ValueError, TypeError):
                expiry_date = None
        
        # Batch and Location
        batch_number = (request.POST.get('batch_number') or '').strip()
        storage_location_id = request.POST.get('storage_location')
        
        category = get_object_or_404(Category, id=category_id)
        location = None
        if storage_location_id:
            location = StorageLocation.objects.filter(id=storage_location_id).first()
        
        product = Product.objects.create(
            name=name,
            category=category,
            unit_price=unit_price,
            description=description,
            stock=stock,
            production_date=production_date,
            best_before_days=best_before_days,
            expiry_date=expiry_date,
            storage_location=location
        )
        # Create inventory record with default threshold
        ProductInventory.objects.get_or_create(
            product=product,
            defaults={
                'low_stock_threshold': 10,
                'sku': f"SKU-{product.id.hex[:6].upper()}"
            }
        )
        
        # Create StockBatch if stock > 0 or a batch number is explicitly provided
        if stock > 0 or batch_number:
            batch_num = batch_number or f"BATCH-{uuid.uuid4().hex[:8].upper()}"
            batch = StockBatch.objects.create(
                product=product,
                batch_number=batch_num,
                quantity=stock,
                initial_quantity=stock,
                production_date=production_date,
                expiry_date=product.expiry_date,
                storage_location=location
            )
            # Re-update to trigger stock calculations
            product.update_stock_from_batches()

            if stock > 0:
                try:
                    InventoryTransaction.objects.create(
                        business=get_default_business(),
                        product=product,
                        batch=batch,
                        transaction_type='received',
                        quantity_change=stock,
                        reference_id=f"BATCH-{batch.batch_number}",
                        notes="Initial stock added on product creation",
                        created_by=str(request.user),
                    )
                except Exception:
                    pass
            
        # Handle Product Image upload to Cloudinary / storage
        image_file = request.FILES.get('product_image')
        image_url = request.POST.get('image_url')
        if image_file or image_url:
            handle_product_image_upload(product, image_file=image_file, image_url=image_url)

        product.refresh_from_db()

        messages.success(request, f"Product '{name}' added to catalog successfully!")
        dispatch_action_notification_and_email(
            actor=request.user,
            title=f"New Product Added: {name}",
            message=f"Product '{name}' was added to catalog.",
            target_obj=product,
            detail_dict={
                "Product Name": name,
                "Category": category.name if category else "Uncategorized",
                "Unit Price": f"₦{unit_price}",
                "Initial Stock": product.stock,
                "Storage Location": location.name if location else "Unplaced",
                "Added By": request.user.get_full_name() or request.user.username or request.user.email
            }
        )
        return redirect('product_list')
    return redirect('product_list')


def handle_product_image_upload(product, image_file=None, image_url=None):
    if not image_file and not image_url:
        return None

    import os
    import cloudinary
    import cloudinary.uploader
    from apps.notifications.models import AlertConfiguration
    from apps.products.models import ProductImage

    config_obj = AlertConfiguration.get_solo()
    creds = config_obj.get_cloudinary_credentials()

    uploaded_url = None

    if creds['is_configured']:
        try:
            cloudinary.config(
                cloud_name=creds['cloud_name'],
                api_key=creds['api_key'],
                api_secret=creds['api_secret'],
                secure=True
            )
            if image_file:
                res = cloudinary.uploader.upload(image_file, folder="products/")
                uploaded_url = res.get('secure_url') or res.get('url')
            elif image_url:
                res = cloudinary.uploader.upload(image_url, folder="products/")
                uploaded_url = res.get('secure_url') or res.get('url')
        except Exception as e:
            print(f"Cloudinary upload exception: {e}")

    # Fallback to local Django storage or direct image_url if Cloudinary wasn't configured or failed:
    if not uploaded_url:
        if image_file:
            from django.core.files.storage import default_storage
            filename = default_storage.save(f"products/{image_file.name}", image_file)
            uploaded_url = default_storage.url(filename)
        elif image_url:
            uploaded_url = image_url

    if uploaded_url:
        ProductImage.objects.filter(product=product, is_primary=True).update(is_primary=False)
        img_obj = ProductImage.objects.create(
            product=product,
            image=uploaded_url,
            is_primary=True
        )
        return img_obj
    return None



@login_required
def product_edit(request, pk):
    if not check_role(request.user, ['admin', 'manager', 'staff']):
        return role_forbidden_response(request, "Permission Denied: View-Only users cannot edit products.")

    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.name = request.POST.get('name')
        category_id = request.POST.get('category')
        product.unit_price = request.POST.get('unit_price')
        product.description = request.POST.get('description')
        
        # Expiry related
        from datetime import date
        prod_date_raw = request.POST.get('production_date', '').strip()
        if prod_date_raw:
            try:
                product.production_date = date.fromisoformat(prod_date_raw)
            except (ValueError, TypeError):
                product.production_date = None
        else:
            product.production_date = None

        best_before_days_raw = request.POST.get('best_before_days')
        try:
            product.best_before_days = int(best_before_days_raw) if best_before_days_raw and str(best_before_days_raw).strip().isdigit() else None
        except (ValueError, TypeError):
            product.best_before_days = None

        exp_date_raw = request.POST.get('expiry_date', '').strip()
        if exp_date_raw:
            try:
                product.expiry_date = date.fromisoformat(exp_date_raw)
            except (ValueError, TypeError):
                product.expiry_date = None
        else:
            product.expiry_date = None
        
        storage_location_id = request.POST.get('storage_location')
        if storage_location_id:
            product.storage_location = StorageLocation.objects.filter(id=storage_location_id).first()
        else:
            product.storage_location = None
            
        if category_id:
            product.category = get_object_or_404(Category, id=category_id)
        
        product.save()

        # Handle Product Image upload / URL
        image_file = request.FILES.get('product_image')
        image_url = request.POST.get('image_url')
        if image_file or image_url:
            handle_product_image_upload(product, image_file=image_file, image_url=image_url)
        
        # Ensure inventory record exists
        ProductInventory.objects.get_or_create(
            product=product,
            defaults={
                'low_stock_threshold': 10,
                'sku': f"SKU-{product.id.hex[:6].upper()}"
            }
        )

        # Handle stock updates across batches
        stock_raw = request.POST.get('stock')
        if stock_raw is not None and str(stock_raw).strip() != '':
            try:
                new_stock = max(0, int(stock_raw))
            except (ValueError, TypeError):
                new_stock = product.stock

            batches = product.batches.all()
            batch_count = batches.count()

            if batch_count == 0:
                if new_stock > 0:
                    batch_num = f"BATCH-{uuid.uuid4().hex[:8].upper()}"
                    batch = StockBatch.objects.create(
                        product=product,
                        batch_number=batch_num,
                        quantity=new_stock,
                        initial_quantity=new_stock,
                        production_date=product.production_date,
                        expiry_date=product.expiry_date,
                        storage_location=product.storage_location
                    )
                    product.update_stock_from_batches()
                    try:
                        InventoryTransaction.objects.create(
                            business=get_default_business(),
                            product=product,
                            batch=batch,
                            transaction_type='received',
                            quantity_change=new_stock,
                            reference_id=f"BATCH-{batch.batch_number}",
                            notes="Initial stock added via product edit",
                            created_by=str(request.user),
                        )
                    except Exception:
                        pass
                else:
                    Product.objects.filter(id=product.id).update(stock=0)
            elif batch_count == 1:
                primary_batch = batches.first()
                old_qty = primary_batch.quantity
                qty_diff = new_stock - old_qty

                primary_batch.quantity = new_stock
                if product.production_date:
                    primary_batch.production_date = product.production_date
                if product.expiry_date:
                    primary_batch.expiry_date = product.expiry_date
                primary_batch.storage_location = product.storage_location
                primary_batch.save()
                product.update_stock_from_batches()

                if qty_diff != 0:
                    try:
                        InventoryTransaction.objects.create(
                            business=get_default_business(),
                            product=product,
                            batch=primary_batch,
                            transaction_type='adjusted',
                            quantity_change=qty_diff,
                            reference_id=f"BATCH-{primary_batch.batch_number}",
                            notes=f"Stock adjusted from {old_qty} to {new_stock} via product edit",
                            created_by=str(request.user),
                        )
                    except Exception:
                        pass
            else:
                # Multiple batches exist
                current_total = product.stock
                qty_diff = new_stock - current_total

                if qty_diff > 0:
                    # User added stock: add diff to the latest batch
                    latest_batch = batches.order_by('-created_at').first()
                    latest_batch.quantity += qty_diff
                    latest_batch.save()
                    product.update_stock_from_batches()

                    try:
                        InventoryTransaction.objects.create(
                            business=get_default_business(),
                            product=product,
                            batch=latest_batch,
                            transaction_type='adjusted',
                            quantity_change=qty_diff,
                            reference_id=f"BATCH-{latest_batch.batch_number}",
                            notes=f"Stock increased by {qty_diff} via product edit",
                            created_by=str(request.user),
                        )
                    except Exception:
                        pass
                elif qty_diff < 0:
                    # User reduced stock: deduct from batches in FEFO order
                    remaining_to_deduct = abs(qty_diff)
                    for b in batches.filter(quantity__gt=0).order_by('expiry_date', 'created_at'):
                        if remaining_to_deduct <= 0:
                            break
                        deduct = min(b.quantity, remaining_to_deduct)
                        b.quantity -= deduct
                        b.save()
                        remaining_to_deduct -= deduct
                    product.update_stock_from_batches()

                    try:
                        InventoryTransaction.objects.create(
                            business=get_default_business(),
                            product=product,
                            transaction_type='adjusted',
                            quantity_change=qty_diff,
                            reference_id=f"ADJ-{product.id.hex[:6].upper()}",
                            notes=f"Stock decreased by {abs(qty_diff)} via product edit",
                            created_by=str(request.user),
                        )
                    except Exception:
                        pass
                else:
                    # Total stock unchanged, keep batch quantities as is
                    pass

        product.refresh_from_db()

        messages.success(request, f"Product '{product.name}' updated successfully!")

        dispatch_action_notification_and_email(
            actor=request.user,
            title=f"Product Updated: {product.name}",
            message=f"Product '{product.name}' details were updated.",
            target_obj=product,
            detail_dict={
                "Product Name": product.name,
                "Category": product.category.name if product.category else "Uncategorized",
                "Unit Price": f"₦{product.unit_price}",
                "Stock": product.stock,
                "Updated By": request.user.get_full_name() or request.user.username or request.user.email
            }
        )
        return redirect('product_list')
    return redirect('product_list')


@login_required
def product_delete(request, pk):
    if not check_role(request.user, ['admin', 'manager']):
        return role_forbidden_response(request, "Permission Denied: Staff and View-Only users cannot delete products.")
        
    product = get_object_or_404(Product, pk=pk)
    
    if request.method != 'POST':
        messages.warning(request, "Product deletion requires POST confirmation.")
        return redirect('product_detail', pk=pk)

    name = product.name
    try:
        product.delete()
        messages.success(request, f"Product '{name}' and all associated stock batches were deleted successfully.")
        
        try:
            dispatch_action_notification_and_email(
                actor=request.user,
                title=f"Product Deleted: {name}",
                message=f"Product '{name}' was deleted from inventory.",
                target_obj=None,
                detail_dict={
                    "Product Name": name,
                    "Deleted By": request.user.get_full_name() or request.user.username or request.user.email
                }
            )
        except Exception as notify_err:
            logger.warning(f"Notification error on product delete: {notify_err}")

    except Exception as e:
        logger.error(f"Error deleting product '{name}': {e}")
        messages.error(request, f"Failed to delete product '{name}': {str(e)}")
        return redirect('product_detail', pk=pk)

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
    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        request.headers.get('HX-Request') == 'true' or
        request.content_type == 'application/json'
    )
    if not check_role(request.user, ['admin', 'manager', 'staff']):
        if is_ajax:
            return JsonResponse({'error': 'Permission Denied: View-Only users cannot create categories.'}, status=403)
        return role_forbidden_response(request, "Permission Denied: View-Only users cannot create categories.")

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        description = (request.POST.get('description') or '').strip()
        if name:
            existing = Category.objects.filter(name__iexact=name).first()
            if existing:
                msg = f"Category '{existing.name}' already exists."
                messages.warning(request, msg)
                if is_ajax:
                    return JsonResponse({
                        'status': 'error',
                        'error': msg,
                        'category': {
                            'id': str(existing.id),
                            'name': existing.name,
                            'description': existing.description
                        }
                    })
                return redirect('category_list')

            try:
                cat = Category.objects.create(name=name, description=description)
                messages.success(request, f"Category '{name}' created successfully!")
                dispatch_action_notification_and_email(
                    actor=request.user,
                    title=f"New Category Created: {name}",
                    message=f"Category '{name}' has been created.",
                    target_obj=cat,
                    detail_dict={
                        "Category Name": name,
                        "Description": description or "None",
                        "Created By": request.user.get_full_name() or request.user.username or request.user.email
                    }
                )
                if is_ajax:
                    return JsonResponse({
                        'status': 'success',
                        'category': {
                            'id': str(cat.id),
                            'name': cat.name,
                            'description': cat.description
                        },
                        'message': f"Category '{name}' created successfully!"
                    })
            except Exception as e:
                msg = f"Category '{name}' already exists or could not be created."
                messages.warning(request, msg)
                if is_ajax:
                    return JsonResponse({'error': msg}, status=400)

        return redirect('category_list')
    return redirect('category_list')


@login_required
def category_edit(request, pk):
    if not check_role(request.user, ['admin', 'manager', 'staff']):
        return role_forbidden_response(request, "Permission Denied: View-Only users cannot edit categories.")

    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        description = (request.POST.get('description') or '').strip()

        if name:
            existing = Category.objects.exclude(pk=category.pk).filter(name__iexact=name).first()
            if existing:
                messages.warning(request, f"Category '{name}' already exists.")
                return redirect('category_list')

            old_name = category.name
            category.name = name
            category.description = description
            category.save()

            messages.success(request, f"Category '{category.name}' updated successfully!")
            dispatch_action_notification_and_email(
                actor=request.user,
                title=f"Category Updated: {category.name}",
                message=f"Category '{old_name}' was updated to '{category.name}'.",
                target_obj=category,
                detail_dict={
                    "Category Name": category.name,
                    "Description": category.description or "None",
                    "Updated By": request.user.get_full_name() or request.user.username or request.user.email
                }
            )
        return redirect('category_list')
    return redirect('category_list')


@login_required
def category_delete(request, pk):
    if not check_role(request.user, ['admin', 'manager']):
        return role_forbidden_response(request, "Permission Denied: Staff and View-Only users cannot delete categories.")

    category = get_object_or_404(Category, pk=pk)
    name = category.name
    category.delete()
    messages.success(request, f"Category '{name}' was deleted successfully.")
    dispatch_action_notification_and_email(
        actor=request.user,
        title=f"Category Deleted: {name}",
        message=f"Category '{name}' was deleted from the system.",
        target_obj=None,
        detail_dict={
            "Category Name": name,
            "Deleted By": request.user.get_full_name() or request.user.username or request.user.email
        }
    )
    return redirect('category_list')


@login_required
def api_categories_list(request):
    categories = list(Category.objects.all().values('id', 'name', 'description'))
    return JsonResponse({'categories': categories})


# Storage Locations (Requirement 2)
@login_required
def storage_location_list(request):
    locations = StorageLocation.objects.all().annotate(
        batch_count=Count('batches'),
        product_count=Count('products')
    )
    if request.method == 'POST':
        if not check_role(request.user, ['admin', 'manager', 'staff']):
            return role_forbidden_response(request, "Permission Denied: View-Only users cannot create storage locations.")
            
        name = request.POST.get('name')
        description = request.POST.get('description')
        temp = request.POST.get('temperature') or None
        hum = request.POST.get('humidity') or None
        
        if name:
            loc = StorageLocation.objects.create(
                name=name,
                description=description,
                temperature=temp,
                humidity=hum
            )
            messages.success(request, f"Storage Location '{name}' created successfully!")
            dispatch_action_notification_and_email(
                actor=request.user,
                title=f"New Storage Location Added: {name}",
                message=f"Storage location '{name}' has been created.",
                target_obj=loc,
                detail_dict={
                    "Location Name": name,
                    "Description": description or "None",
                    "Temperature": f"{temp}°C" if temp else "N/A",
                    "Humidity": f"{hum}%" if hum else "N/A",
                    "Added By": request.user.get_full_name() or request.user.username or request.user.email
                }
            )
        return redirect('storage_location_list')
        
    return render(request, 'core/storage_locations.html', {'locations': locations})


@login_required
def storage_location_edit(request, pk):
    if not check_role(request.user, ['admin', 'manager', 'staff']):
        return role_forbidden_response(request, "Permission Denied: View-Only users cannot edit storage locations.")
        
    location = get_object_or_404(StorageLocation, pk=pk)
    if request.method == 'POST':
        location.name = request.POST.get('name')
        location.description = request.POST.get('description')
        location.temperature = request.POST.get('temperature') or None
        location.humidity = request.POST.get('humidity') or None
        location.save()
        messages.success(request, f"Storage Location '{location.name}' updated successfully!")
    return redirect('storage_location_list')


@login_required
def storage_location_delete(request, pk):
    if not check_role(request.user, ['admin', 'manager']):
        return role_forbidden_response(request, "Permission Denied: Staff and View-Only users cannot delete storage locations.")
        
    location = get_object_or_404(StorageLocation, pk=pk)
    name = location.name
    location.delete()
    messages.success(request, f"Storage Location '{name}' was deleted successfully.")
    return redirect('storage_location_list')


@login_required
def settings_page(request):
    config_obj = AlertConfiguration.get_solo()
    from django.conf import settings
    resend_configured = bool(getattr(settings, 'RESEND_API_KEY', None))
    cloudinary_creds = config_obj.get_cloudinary_credentials()
    return render(request, 'core/settings.html', {
        'config': config_obj,
        'resend_configured': resend_configured,
        'cloudinary_creds': cloudinary_creds
    })


@login_required
def settings_update(request):
    if not check_role(request.user, ['admin']):
        return role_forbidden_response(request, "Permission Denied: Only Administrators can configure system settings.")
        
    if request.method == 'POST':
        config_obj = AlertConfiguration.get_solo()
        config_obj.critical_threshold_days = int(request.POST.get('critical_threshold_days', 7))
        config_obj.high_threshold_days = int(request.POST.get('high_threshold_days', 30))
        config_obj.medium_threshold_days = int(request.POST.get('medium_threshold_days', 60))
        config_obj.recipient_emails = request.POST.get('recipient_emails', '')
        config_obj.recipient_phones = request.POST.get('recipient_phones', '')
        config_obj.escalation_hours = int(request.POST.get('escalation_hours', 24))
        config_obj.escalation_email = request.POST.get('escalation_email', '')
        config_obj.sms_provider_url = request.POST.get('sms_provider_url', '')
        config_obj.sms_api_key = request.POST.get('sms_api_key', '')
        
        # Cloudinary integration fields
        config_obj.cloudinary_cloud_name = request.POST.get('cloudinary_cloud_name', '').strip()
        config_obj.cloudinary_api_key = request.POST.get('cloudinary_api_key', '').strip()
        config_obj.cloudinary_api_secret = request.POST.get('cloudinary_api_secret', '').strip()
        
        config_obj.save()
        
        # Trigger retraining when settings change
        try:
            train_expiry_model()
            messages.success(request, "Alert thresholds & Cloudinary settings updated; AI Model retrained successfully!")
        except Exception as e:
            messages.success(request, "Settings updated successfully!")

            
    return redirect('settings_page')


@login_required
def business_list(request):
    businesses = Business.objects.all().order_by('-created_at')
    return render(request, 'core/business_list.html', {'businesses': businesses})


@login_required
def business_create(request):
    if not check_role(request.user, ['admin']):
        return role_forbidden_response(request, "Permission Denied: Only Administrators can register businesses.")

    if request.method == 'POST':
        name = request.POST.get('name')
        subdomain = request.POST.get('subdomain')
        if name and subdomain:
            biz = Business.objects.create(name=name, subdomain=subdomain)
            messages.success(request, f"Business '{name}' created successfully!")
            dispatch_action_notification_and_email(
                actor=request.user,
                title=f"New Business Registered: {name}",
                message=f"Business '{name}' with subdomain '{subdomain}' was registered.",
                target_obj=biz,
                detail_dict={
                    "Business Name": name,
                    "Subdomain": subdomain,
                    "Registered By": request.user.get_full_name() or request.user.username or request.user.email
                }
            )
        return redirect('business_list')
    return redirect('business_list')


# Alerts & Audit Log Views (Requirement 7)
@login_required
def notifications_page(request):
    alerts = AlertLog.objects.select_related('batch__product', 'acknowledged_by', 'resolved_by').all()
    in_app = Notification.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'core/notifications.html', {
        'alerts': alerts,
        'notifications': in_app
    })


@login_required
def alert_acknowledge(request, pk):
    if not check_role(request.user, ['admin', 'manager', 'staff']):
        return role_forbidden_response(request, "Permission Denied: View-Only users cannot acknowledge alerts.")
        
    alert = get_object_or_404(AlertLog, pk=pk)
    alert.status = 'acknowledged'
    alert.acknowledged_at = timezone.now()
    alert.acknowledged_by = request.user
    alert.save()
    messages.success(request, f"Alert for '{alert.batch.product.name}' was acknowledged.")
    return redirect('notifications')


@login_required
def alert_resolve(request, pk):
    if not check_role(request.user, ['admin', 'manager', 'staff']):
        return role_forbidden_response(request, "Permission Denied: View-Only users cannot resolve alerts.")
        
    alert = get_object_or_404(AlertLog, pk=pk)
    alert.status = 'resolved'
    alert.resolved_at = timezone.now()
    alert.resolved_by = request.user
    
    # Also clear quantity of this batch if resolved (marking expired or discarded)
    batch = alert.batch
    batch.quantity = 0
    batch.save()
    batch.product.update_stock_from_batches()
    
    alert.save()
    messages.success(request, f"Alert for '{alert.batch.product.name}' was resolved and batch was discarded.")
    return redirect('notifications')


# Exporting Reports in CSV and PDF formats (Requirement 10)
@login_required
def export_report(request, report_type, export_format):
    today_str = timezone.now().strftime("%Y-%m-%d")
    
    # 1. Fetch data based on report type
    if report_type == 'expiry':
        title = "Expiry Risk Report"
        headers = ["Product Name", "Batch Number", "Expiry Date", "Days Left", "Risk Tier", "Probability"]
        batches = StockBatch.objects.filter(quantity__gt=0).select_related('product').order_by('expiry_date')
        data_rows = []
        for b in batches:
            days_left = (b.expiry_date - timezone.now().date()).days if b.expiry_date else "N/A"
            data_rows.append([
                b.product.name,
                b.batch_number,
                b.expiry_date.strftime("%Y-%m-%d") if b.expiry_date else "N/A",
                str(days_left),
                b.risk_tier.upper(),
                f"{b.risk_probability:.1%}"
            ])
    elif report_type == 'low_stock':
        title = "Low Stock Report"
        headers = ["Product Name", "Category", "Current Stock", "Threshold", "Unit Price"]
        products = Product.objects.filter(stock__lte=F('inventory__low_stock_threshold')).select_related('category', 'inventory')
        data_rows = []
        for p in products:
            data_rows.append([
                p.name,
                p.category.name if p.category else "Uncategorized",
                str(p.stock),
                str(p.inventory.low_stock_threshold) if hasattr(p, 'inventory') else "N/A",
                format_naira(p.unit_price)
            ])
    else:  # 'products' or full inventory
        title = "Inventory Valuation Report"
        headers = ["Product Name", "Category", "Current Stock", "Unit Price", "Total Value", "Expiry Date"]
        products = Product.objects.all().select_related('category')
        data_rows = []
        for p in products:
            data_rows.append([
                p.name,
                p.category.name if p.category else "Uncategorized",
                str(p.stock),
                format_naira(p.unit_price),
                format_naira(p.stock * p.unit_price),
                p.expiry_date.strftime("%Y-%m-%d") if p.expiry_date else "N/A"
            ])
            
    # 2. Render as CSV
    if export_format == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{report_type}_report_{today_str}.csv"'
        writer = csv.writer(response)
        writer.writerow([title])
        writer.writerow([f"Generated on: {timezone.now().strftime('%Y-%m-%d %H:%M')}"])
        writer.writerow([])
        writer.writerow(headers)
        for row in data_rows:
            writer.writerow(row)
        return response
        
    # 3. Render as PDF (using ReportLab)
    elif export_format == 'pdf':
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{report_type}_report_{today_str}.pdf"'
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        story = []
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            name='TitleStyle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=18,
            textColor=colors.HexColor('#d4af37'), # yellow-600 color
            spaceAfter=6
        )
        meta_style = ParagraphStyle(
            name='MetaStyle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            textColor=colors.gray,
            spaceAfter=20
        )
        
        story.append(Paragraph(title, title_style))
        story.append(Paragraph(f"Generated on: {timezone.now().strftime('%Y-%m-%d %H:%M')} | M_D Chippa Compliance Report", meta_style))
        
        # Build Table
        table_data = [headers] + data_rows
        t = Table(table_data, colWidths=[150, 90, 80, 70, 70, 70] if report_type == 'expiry' else None)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d4af37')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fafafa')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ]))
        
        story.append(t)
        doc.build(story)
        
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        return response
        
    return redirect('dashboard')


@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.mark_as_read()
    if request.headers.get('HX-Request'):
        return HttpResponse("")
    if notification.action_url:
        return redirect(notification.action_url)
    return redirect('/notifications/?tab=inbox')


@login_required
def mark_all_notifications_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    if request.headers.get('HX-Request'):
        return HttpResponse("")
    return redirect('/notifications/?tab=inbox')


@login_required
def simulate_expiry_alerts(request):
    if not check_role(request.user, ['admin']):
        return role_forbidden_response(request, "Permission Denied: Only Administrators can run simulations.")
        
    if request.method == 'POST':
        from datetime import timedelta
        from apps.notifications.alerts import check_and_generate_alerts, check_and_send_expiry_milestone_emails
        from apps.products.ml import run_expiry_predictions_for_all_batches
        from apps.notifications.models import ExpiryMilestone
        
        # 1. Clear previous logs so that clicking the button again will trigger alerts fresh!
        AlertLog.objects.all().delete()
        ExpiryMilestone.objects.all().delete()
        Notification.objects.all().delete()
        
        today = timezone.now().date()
        
        # 2. Check if there are any products/batches in the database
        active_batch_count = StockBatch.objects.filter(quantity__gt=0).count()
        
        if active_batch_count == 0:
            # Seed a test product and batches if database is empty
            category, _ = Category.objects.get_or_create(
                name="Test Category",
                defaults={"description": "Test Category"}
            )
            product = Product.objects.create(
                name="Test Near-Expiry Product",
                category=category,
                unit_price=150.00,
                description="Test product created automatically because no products existed.",
                stock=40
            )
            ProductInventory.objects.get_or_create(product=product, defaults={"low_stock_threshold": 10})
            
            milestones = [7, 5, 3, 1]
            for days in milestones:
                StockBatch.objects.create(
                    product=product,
                    batch_number=f"TEST-BATCH-{days}D",
                    quantity=10,
                    initial_quantity=10,
                    production_date=today - timedelta(days=10),
                    expiry_date=today + timedelta(days=days)
                )
            product.update_stock_from_batches()
        else:
            # Check if any active batch is expiring within 30 days
            near_expiry_count = StockBatch.objects.filter(
                quantity__gt=0,
                expiry_date__isnull=False,
                expiry_date__lte=today + timedelta(days=30),
                expiry_date__gte=today
            ).count()
            
            # If no existing batches are expiring soon, update the first 4 active batches to expire in 7, 5, 3, 1 days
            if near_expiry_count == 0:
                active_batches = list(StockBatch.objects.filter(quantity__gt=0).order_by('id')[:4])
                milestones = [7, 5, 3, 1]
                for idx, batch in enumerate(active_batches):
                    days = milestones[idx] if idx < len(milestones) else 1
                    batch.expiry_date = today + timedelta(days=days)
                    batch.save()
                    batch.product.update_stock_from_batches()
        
        # 3. Recalculate predictions and risk levels (this sets critical and high risk tiers)
        run_expiry_predictions_for_all_batches()
        
        # 4. Trigger the actual alert scanners on the existing database batches
        alerts_gen, alerts_disp = check_and_generate_alerts()
        emails_sent = check_and_send_expiry_milestone_emails()
        
        messages.success(
            request, 
            f"Alert scanner run successfully! Scanned all products: generated {alerts_gen} risk alerts and {emails_sent} milestone warnings."
        )
        return redirect('notifications')
        
    return redirect('settings_page')


@login_required
def clear_simulation_data(request):
    if not check_role(request.user, ['admin']):
        return role_forbidden_response(request, "Permission Denied: Only Administrators can clear simulation data.")
        
    if request.method == 'POST':
        from apps.notifications.models import ExpiryMilestone
        
        # Clear all alerts, milestones, and notifications to allow testing the scanner again!
        AlertLog.objects.all().delete()
        ExpiryMilestone.objects.all().delete()
        Notification.objects.all().delete()
        
        messages.success(request, "All alerts, milestone logs, and in-app notifications have been cleared successfully.")
        return redirect('/settings/?tab=simulation')
        
    return redirect('settings_page')


