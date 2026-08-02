from django.urls import path
from . import views
from . import batch_views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('products/', views.product_list, name='product_list'),
    path('products/<uuid:pk>/', batch_views.product_detail_with_batches, name='product_detail'),
    path('products/<uuid:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<uuid:pk>/delete/', views.product_delete, name='product_delete'),
    path('products/add/', views.product_add, name='product_add'),
    
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.category_add, name='category_add'),
    path('categories/<uuid:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<uuid:pk>/delete/', views.category_delete, name='category_delete'),
    path('api/categories/', views.api_categories_list, name='api_categories'),
    
    # Storage Locations (Requirement 2)
    path('locations/', views.storage_location_list, name='storage_location_list'),
    path('locations/<uuid:pk>/edit/', views.storage_location_edit, name='storage_location_edit'),
    path('locations/<uuid:pk>/delete/', views.storage_location_delete, name='storage_location_delete'),
    
    # System settings (Requirement 9)
    path('settings/', views.settings_page, name='settings_page'),
    path('settings/update/', views.settings_update, name='settings_update'),
    
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
    path('reports/export/<str:report_type>/<str:export_format>/', views.export_report, name='export_report'),
    
    # Suppliers & Transfers
    path('suppliers/', batch_views.suppliers_list, name='suppliers'),
    path('stock-transfers/', batch_views.stock_transfers_list, name='stock_transfers'),
    
    # Notifications & Alerts Audit Log (Requirement 7)
    path('notifications/', views.notifications_page, name='notifications'),
    path('alerts/<uuid:pk>/acknowledge/', views.alert_acknowledge, name='alert_acknowledge'),
    path('alerts/<uuid:pk>/resolve/', views.alert_resolve, name='alert_resolve'),
    path('notifications/<int:pk>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/read-all/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('settings/simulate-expiry/', views.simulate_expiry_alerts, name='simulate_expiry_alerts'),
    path('settings/clear-simulation/', views.clear_simulation_data, name='clear_simulation_data'),
]
