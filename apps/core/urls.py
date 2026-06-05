from django.urls import path
from . import views
from . import batch_views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('products/', views.product_list, name='product_list'),
    path('products/<uuid:pk>/', batch_views.product_detail_with_batches, name='product_detail'),
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.category_add, name='category_add'),
    path('settings/', views.settings_page, name='settings_page'),
    path('products/add/', views.product_add, name='product_add'),
    path('products/<uuid:pk>/edit/', views.product_edit, name='product_edit'),
    path('businesses/', views.business_list, name='business_list'),
    path('businesses/add/', views.business_create, name='business_create'),
    
    # New batch management & supply chain URLs
    path('batches/', batch_views.batch_management, name='batch_management'),
    path('batches/<uuid:batch_id>/', batch_views.batch_detail, name='batch_detail'),
    path('batches/<uuid:batch_id>/adjust/', batch_views.adjust_batch_quantity, name='adjust_batch'),
    path('batches/<uuid:batch_id>/mark-expired/', batch_views.mark_batch_expired, name='mark_batch_expired'),
    
    # Purchase Orders & Receiving
    path('purchase-orders/', batch_views.purchase_orders_list, name='purchase_orders'),
    
    # Reports
    path('reports/expiry/', batch_views.expiry_report, name='expiry_report'),
    path('reports/low-stock/', batch_views.low_stock_report, name='low_stock_report'),
    
    # Suppliers & Transfers
    path('suppliers/', batch_views.suppliers_list, name='suppliers'),
    path('stock-transfers/', batch_views.stock_transfers_list, name='stock_transfers'),
    
    # Notifications
    path('notifications/', views.notifications_page, name='notifications'),
]
