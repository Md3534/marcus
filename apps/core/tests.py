from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from apps.products.models import Product, Category, StockBatch, ProductInventory, StorageLocation
from apps.notifications.models import AlertConfiguration, AlertLog, Notification
from apps.notifications.alerts import check_and_generate_alerts, check_and_send_expiry_milestone_emails
from utils.email import send_resend_email

User = get_user_model()

class InventoryManagementFeaturesTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='admin_test@example.com',
            password='password123',
            role='admin'
        )
        self.client.login(email='admin_test@example.com', password='password123')

        
        self.category = Category.objects.create(name='Beverages', description='Drinks and juices')
        self.location = StorageLocation.objects.create(name='Shelf A1', description='Main Store Shelf A1')
        
        self.product = Product.objects.create(
            name='Test Orange Juice',
            category=self.category,
            unit_price=250.00,
            stock=100,
            storage_location=self.location
        )
        ProductInventory.objects.create(product=self.product, sku='SKU-JUICE-001', low_stock_threshold=10)

    def test_add_product_batch(self):
        """Test adding a product batch via add_batch view"""
        url = reverse('add_batch', kwargs={'pk': self.product.id})
        response = self.client.post(url, {
            'batch_number': 'BATCH-ORANGE-01',
            'quantity': 50,
            'production_date': str(timezone.now().date() - timedelta(days=10)),
            'expiry_date': str(timezone.now().date() + timedelta(days=10)),
            'storage_location': str(self.location.id)
        })
        self.assertEqual(response.status_code, 302)
        
        batch = StockBatch.objects.get(batch_number='BATCH-ORANGE-01')
        self.assertEqual(batch.quantity, 50)
        self.assertEqual(batch.product, self.product)
        self.assertEqual(self.product.batches.count(), 1)

    def test_products_search_and_filter(self):
        """Test searching and filtering in product_list view"""
        Product.objects.create(name='Fresh Apple Milk', category=self.category, unit_price=100, stock=0)
        
        # Test search query
        response = self.client.get(reverse('product_list'), {'search': 'Orange'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Orange Juice')
        self.assertNotContains(response, 'Fresh Apple Milk')
        
        # Test stock_status filter
        response_out = self.client.get(reverse('product_list'), {'stock_status': 'out_of_stock'})
        self.assertEqual(response_out.status_code, 200)
        self.assertContains(response_out, 'Fresh Apple Milk')
        self.assertNotContains(response_out, 'Test Orange Juice')

    def test_resend_expiry_alert_dispatched(self):
        """Test that expiry alert sends email to registered users via Resend without error"""
        batch = StockBatch.objects.create(
            product=self.product,
            batch_number='BATCH-RISK-01',
            quantity=10,
            initial_quantity=10,
            expiry_date=timezone.now().date() + timedelta(days=3),
            risk_tier='critical',
            risk_probability=0.95
        )
        
        # Trigger alert generator
        gen_count, disp_count = check_and_generate_alerts()
        self.assertGreaterEqual(gen_count, 1)
        self.assertTrue(AlertLog.objects.filter(batch=batch).exists())

    def test_product_deletion_workflow(self):
        """Test deleting a product requires POST and deletes associated batches"""
        StockBatch.objects.create(
            product=self.product,
            batch_number='BATCH-DELETE-ME',
            quantity=20,
            expiry_date=timezone.now().date() + timedelta(days=5)
        )
        delete_url = reverse('product_delete', kwargs={'pk': self.product.id})
        
        # GET request should fail / warn
        get_res = self.client.get(delete_url)
        self.assertEqual(get_res.status_code, 302)
        self.assertTrue(Product.objects.filter(id=self.product.id).exists())
        
        # POST request should succeed
        post_res = self.client.post(delete_url)
        self.assertEqual(post_res.status_code, 302)
        self.assertFalse(Product.objects.filter(id=self.product.id).exists())
        self.assertFalse(StockBatch.objects.filter(batch_number='BATCH-DELETE-ME').exists())
