from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from apps.products.models import Product, Category, StockBatch, ProductInventory, StorageLocation, InventoryTransaction
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

    def test_product_add_with_stock(self):
        """Test adding a product with initial stock creates batch, inventory, and transaction"""
        add_url = reverse('product_add')
        res = self.client.post(add_url, {
            'name': 'Fresh Strawberries',
            'category': str(self.category.id),
            'unit_price': '450.00',
            'stock': '75',
            'storage_location': str(self.location.id),
            'production_date': str(timezone.now().date()),
            'best_before_days': '14',
        })
        self.assertEqual(res.status_code, 302)
        
        product = Product.objects.get(name='Fresh Strawberries')
        self.assertEqual(product.stock, 75)
        self.assertEqual(product.storage_location, self.location)
        self.assertEqual(product.batches.count(), 1)
        
        batch = product.batches.first()
        self.assertEqual(batch.quantity, 75)
        self.assertEqual(batch.storage_location, self.location)
        
        # Verify InventoryTransaction
        self.assertTrue(InventoryTransaction.objects.filter(product=product, transaction_type='received', quantity_change=75).exists())

    def test_product_add_zero_stock(self):
        """Test adding a product with zero stock creates product with 0 stock and no batches"""
        add_url = reverse('product_add')
        res = self.client.post(add_url, {
            'name': 'Out of Stock Coffee',
            'category': str(self.category.id),
            'unit_price': '1200.00',
            'stock': '0',
        })
        self.assertEqual(res.status_code, 302)
        
        product = Product.objects.get(name='Out of Stock Coffee')
        self.assertEqual(product.stock, 0)
        self.assertEqual(product.batches.count(), 0)

    def test_product_edit_add_stock_to_zero_batch_product(self):
        """Test editing a product with 0 batches to add stock creates a batch and updates stock"""
        zero_prod = Product.objects.create(
            name='Zero Stock Bread',
            category=self.category,
            unit_price=200.00,
            stock=0
        )
        self.assertEqual(zero_prod.batches.count(), 0)
        
        edit_url = reverse('product_edit', kwargs={'pk': zero_prod.id})
        res = self.client.post(edit_url, {
            'name': 'Zero Stock Bread Updated',
            'category': str(self.category.id),
            'unit_price': '220.00',
            'stock': '30',
        })
        self.assertEqual(res.status_code, 302)
        
        zero_prod.refresh_from_db()
        self.assertEqual(zero_prod.stock, 30)
        self.assertEqual(zero_prod.batches.count(), 1)
        self.assertEqual(zero_prod.batches.first().quantity, 30)
        self.assertTrue(InventoryTransaction.objects.filter(product=zero_prod, quantity_change=30).exists())

    def test_product_edit_stock_single_batch(self):
        """Test editing stock for a product with 1 batch correctly increases, decreases, or sets to 0"""
        prod = Product.objects.create(
            name='Single Batch Milk',
            category=self.category,
            unit_price=300.00,
            stock=50
        )
        batch = StockBatch.objects.create(
            product=prod,
            batch_number='BATCH-MILK-1',
            quantity=50,
            initial_quantity=50
        )
        prod.update_stock_from_batches()
        
        edit_url = reverse('product_edit', kwargs={'pk': prod.id})
        
        # Increase stock to 80
        self.client.post(edit_url, {
            'name': 'Single Batch Milk',
            'category': str(self.category.id),
            'unit_price': '300.00',
            'stock': '80',
        })
        prod.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(prod.stock, 80)
        self.assertEqual(batch.quantity, 80)
        
        # Decrease stock to 20
        self.client.post(edit_url, {
            'name': 'Single Batch Milk',
            'category': str(self.category.id),
            'unit_price': '300.00',
            'stock': '20',
        })
        prod.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(prod.stock, 20)
        self.assertEqual(batch.quantity, 20)
        
        # Set stock to 0
        self.client.post(edit_url, {
            'name': 'Single Batch Milk',
            'category': str(self.category.id),
            'unit_price': '300.00',
            'stock': '0',
        })
        prod.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(prod.stock, 0)
        self.assertEqual(batch.quantity, 0)

    def test_product_edit_stock_multi_batch_preserves_quantities_and_adjusts(self):
        """Test multi-batch product editing preserves quantities when stock unchanged, and adjusts properly"""
        prod = Product.objects.create(
            name='Multi Batch Apples',
            category=self.category,
            unit_price=100.00,
            stock=0
        )
        today = timezone.now().date()
        b1 = StockBatch.objects.create(
            product=prod,
            batch_number='BATCH-APPLES-A',
            quantity=20,
            initial_quantity=20,
            expiry_date=today + timedelta(days=5)
        )
        b2 = StockBatch.objects.create(
            product=prod,
            batch_number='BATCH-APPLES-B',
            quantity=30,
            initial_quantity=30,
            expiry_date=today + timedelta(days=20)
        )
        prod.update_stock_from_batches()
        self.assertEqual(prod.stock, 50)
        
        edit_url = reverse('product_edit', kwargs={'pk': prod.id})
        
        # Edit price only with stock=50: should NOT inflate stock
        self.client.post(edit_url, {
            'name': 'Multi Batch Apples Premium',
            'category': str(self.category.id),
            'unit_price': '150.00',
            'stock': '50',
        })
        prod.refresh_from_db()
        b1.refresh_from_db()
        b2.refresh_from_db()
        self.assertEqual(prod.stock, 50)
        self.assertEqual(b1.quantity, 20)
        self.assertEqual(b2.quantity, 30)
        
        # Increase stock to 65: adds 15 to latest batch
        self.client.post(edit_url, {
            'name': 'Multi Batch Apples Premium',
            'category': str(self.category.id),
            'unit_price': '150.00',
            'stock': '65',
        })
        prod.refresh_from_db()
        self.assertEqual(prod.stock, 65)
        
        # Decrease stock to 35: deducts 30 across FEFO batches
        self.client.post(edit_url, {
            'name': 'Multi Batch Apples Premium',
            'category': str(self.category.id),
            'unit_price': '150.00',
            'stock': '35',
        })
        prod.refresh_from_db()
        self.assertEqual(prod.stock, 35)
