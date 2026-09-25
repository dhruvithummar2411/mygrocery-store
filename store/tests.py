from django.test import TestCase, Client
from django.contrib.auth.models import User
from store.models import Order, OrderItem
from decimal import Decimal

class MyBillsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='cust1', password='password123')
        self.other_user = User.objects.create_user(username='cust2', password='password123')

    def test_empty_bills_unauthenticated(self):
        resp = self.client.get('/my-bills/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'No Previous Bills')

    def test_empty_bills_authenticated(self):
        self.client.force_login(self.user)
        resp = self.client.get('/my-bills/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'No Previous Bills')

    def test_my_bills_displays_orders_and_buttons(self):
        order = Order.objects.create(
            user=self.user,
            customer_name='Cust One',
            total_amount=Decimal('150.00'),
            paid_amount=Decimal('150.00'),
            status='Ordered'
        )
        OrderItem.objects.create(
            order=order,
            product_name='Fresh Milk 1L',
            qty=2,
            price=Decimal('75.00')
        )

        self.client.force_login(self.user)
        resp = self.client.get('/my-bills/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'Bill #{order.id}')
        self.assertContains(resp, 'Fresh Milk 1L')
        self.assertContains(resp, f'/bill/{order.id}/')
        self.assertContains(resp, f'/bill/{order.id}/?download=true')
        self.assertContains(resp, f'/delete-bill/{order.id}/')

    def test_user_cannot_see_other_user_bills(self):
        Order.objects.create(
            user=self.other_user,
            customer_name='Cust Two',
            total_amount=Decimal('80.00'),
            paid_amount=Decimal('80.00'),
            status='Ordered'
        )
        self.client.force_login(self.user)
        resp = self.client.get('/my-bills/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'No Previous Bills')

    def test_delete_bill(self):
        order = Order.objects.create(
            user=self.user,
            customer_name='Cust One',
            total_amount=Decimal('120.00'),
            paid_amount=Decimal('120.00')
        )
        self.client.force_login(self.user)
        resp = self.client.post(f'/delete-bill/{order.id}/', follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Order.objects.filter(id=order.id).exists())
        self.assertContains(resp, 'No Previous Bills')

    def test_my_orders_shows_only_active_orders(self):
        active_order = Order.objects.create(
            user=self.user,
            customer_name='Cust One',
            total_amount=Decimal('100.00'),
            paid_amount=Decimal('100.00'),
            status='Ordered'
        )
        delivered_order = Order.objects.create(
            user=self.user,
            customer_name='Cust One',
            total_amount=Decimal('200.00'),
            paid_amount=Decimal('200.00'),
            status='Delivered'
        )

        self.client.force_login(self.user)

        # 1. Check My Orders: only active_order should appear, delivered_order must be hidden
        resp_orders = self.client.get('/my-orders/')
        self.assertEqual(resp_orders.status_code, 200)
        self.assertContains(resp_orders, f'Order #{active_order.id}')
        self.assertNotContains(resp_orders, f'Order #{delivered_order.id}')

        # 2. Check My Bills: both active and delivered orders appear
        resp_bills = self.client.get('/my-bills/')
        self.assertEqual(resp_bills.status_code, 200)
        self.assertContains(resp_bills, f'Bill #{active_order.id}')
        self.assertContains(resp_bills, f'Bill #{delivered_order.id}')

    def test_delivered_order_auto_leaves_my_orders(self):
        order = Order.objects.create(
            user=self.user,
            customer_name='Cust One',
            total_amount=Decimal('150.00'),
            status='Shipped'
        )
        self.client.force_login(self.user)

        # While shipped, order is visible in My Orders
        resp1 = self.client.get('/my-orders/')
        self.assertContains(resp1, f'Order #{order.id}')

        # Mark as Delivered
        order.status = 'Delivered'
        order.save()

        # Now it is automatically gone from My Orders
        resp2 = self.client.get('/my-orders/')
        self.assertNotContains(resp2, f'Order #{order.id}')
        self.assertContains(resp2, 'No Active Orders')

        # And it is present in My Bills
        resp3 = self.client.get('/my-bills/')
        self.assertContains(resp3, f'Bill #{order.id}')

    def test_delete_removes_from_both_places(self):
        order = Order.objects.create(
            user=self.user,
            customer_name='Cust One',
            total_amount=Decimal('100.00'),
            status='Packed'
        )
        self.client.force_login(self.user)

        # Verify present in both My Orders and My Bills
        self.assertContains(self.client.get('/my-orders/'), f'Order #{order.id}')
        self.assertContains(self.client.get('/my-bills/'), f'Bill #{order.id}')

        # Delete from My Orders
        del_resp = self.client.post(f'/delete-bill/{order.id}/', HTTP_REFERER='http://testserver/my-orders/', follow=True)
        self.assertEqual(del_resp.status_code, 200)

        # Order must be deleted from DB
        self.assertFalse(Order.objects.filter(id=order.id).exists())

        # Disappeared from both My Orders and My Bills
        self.assertNotContains(self.client.get('/my-orders/'), f'Order #{order.id}')
        self.assertNotContains(self.client.get('/my-bills/'), f'Bill #{order.id}')


class SecurityPaymentTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.normal_user = User.objects.create_user(username='customer', password='password123')
        self.staff_user = User.objects.create_user(username='admin_staff', password='password123', is_staff=True)
        self.order = Order.objects.create(
            user=self.normal_user,
            customer_name='Customer Test',
            customer_phone='9999999999',
            total_amount=Decimal('500.00'),
            paid_amount=Decimal('0.00'),
            status='Ordered'
        )

    def test_normal_user_cannot_see_record_payment_button(self):
        self.client.force_login(self.normal_user)
        resp = self.client.get(f'/bill/{self.order.id}/')
        self.assertEqual(resp.status_code, 200)
        # Should see COD amount to collect box
        self.assertContains(resp, 'Amount to Collect')
        # Should NOT see the Record Payment button or form
        self.assertNotContains(resp, 'Record Payment')
        self.assertNotContains(resp, f'/record-cash/{self.order.id}/')

    def test_staff_user_sees_record_payment_button(self):
        self.client.force_login(self.staff_user)
        resp = self.client.get(f'/bill/{self.order.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Amount to Collect')
        self.assertContains(resp, 'Record Payment')
        self.assertContains(resp, f'/record-cash/{self.order.id}/')

    def test_normal_user_direct_post_blocked(self):
        self.client.force_login(self.normal_user)
        resp = self.client.post(f'/record-cash/{self.order.id}/', {'cash_amount': '500.00'})
        self.assertEqual(resp.status_code, 403)
        self.order.refresh_from_db()
        self.assertFalse(self.order.cash_collected)
        self.assertEqual(self.order.payment_status, 'PENDING')

    def test_unauthenticated_direct_post_blocked(self):
        resp = self.client.post(f'/record-cash/{self.order.id}/', {'cash_amount': '500.00'})
        self.assertEqual(resp.status_code, 403)
        self.order.refresh_from_db()
        self.assertFalse(self.order.cash_collected)
        self.assertEqual(self.order.payment_status, 'PENDING')

    def test_staff_user_can_record_payment(self):
        self.client.force_login(self.staff_user)
        resp = self.client.post(f'/record-cash/{self.order.id}/', {'cash_amount': '500.00'})
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertTrue(self.order.cash_collected)
        self.assertEqual(self.order.payment_status, 'PAID')
        self.assertEqual(self.order.paid_amount, Decimal('500.00'))

    def test_normal_user_bill_post_blocked(self):
        self.client.force_login(self.normal_user)
        resp = self.client.post(f'/bill/{self.order.id}/', {'action': 'record_cash', 'cash_received': '500.00'})
        self.assertEqual(resp.status_code, 403)
        self.order.refresh_from_db()
        self.assertFalse(self.order.cash_collected)
        self.assertEqual(self.order.payment_status, 'PENDING')


class WishlistTests(TestCase):
    def setUp(self):
        from store.models import Category, Product, Wishlist
        self.client = Client()
        self.user = User.objects.create_user(username='wishlist_user', password='password123')
        self.category = Category.objects.create(name='Dairy')
        self.product1 = Product.objects.create(name='Fresh Milk 500ml', price=30, category=self.category, stock=10)
        self.product2 = Product.objects.create(name='Paneer 200g', price=90, category=self.category, stock=5)

    def test_wishlist_unauthenticated_redirects(self):
        resp = self.client.get('/wishlist/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_wishlist_ajax_unauthenticated(self):
        resp = self.client.get(f'/wishlist/add/{self.product1.id}/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get('status'), 'login_required')

    def test_add_and_remove_wishlist_authenticated(self):
        from store.models import Wishlist
        self.client.force_login(self.user)
        
        # 1. Add product1 to wishlist via AJAX
        resp = self.client.get(f'/wishlist/add/{self.product1.id}/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('status'), 'added')
        self.assertEqual(data.get('count'), 1)
        self.assertTrue(Wishlist.objects.filter(user=self.user, product=self.product1).exists())

        # 2. Toggle product1 again via AJAX -> removes it
        resp2 = self.client.get(f'/wishlist/add/{self.product1.id}/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(data2.get('status'), 'removed')
        self.assertEqual(data2.get('count'), 0)
        self.assertFalse(Wishlist.objects.filter(user=self.user, product=self.product1).exists())

        # 3. Add back and check wishlist page view
        Wishlist.objects.create(user=self.user, product=self.product2)
        page_resp = self.client.get('/wishlist/')
        self.assertEqual(page_resp.status_code, 200)
        self.assertContains(page_resp, 'Paneer 200g')
        self.assertContains(page_resp, 'My Wishlist')

        # 4. Remove via remove_from_wishlist view
        del_resp = self.client.get(f'/wishlist/remove/{self.product2.id}/')
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(Wishlist.objects.filter(user=self.user, product=self.product2).exists())



