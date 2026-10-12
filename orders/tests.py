from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Address
from orders.models import DeliverySlot, OfflinePaymentCollection, Order, OrderItem
from products.models import Category, Product
from subscriptions.models import Payment, Subscription

User = get_user_model()


class OfflinePaymentSystemTests(APITestCase):

    def setUp(self):
        # 1. Customer
        self.customer = User.objects.create_user(
            username='9876543210',
            mobile_number='9876543210',
            password='password123',
            first_name='Rahul',
            last_name='Patil',
            role='customer',
        )

        # 2. Delivery Partner A
        self.delivery_a = User.objects.create_user(
            username='9998887771',
            mobile_number='9998887771',
            password='password123',
            first_name='Amit',
            last_name='Kumar',
            role='delivery_boy',
        )

        # 3. Delivery Partner B
        self.delivery_b = User.objects.create_user(
            username='9998887772',
            mobile_number='9998887772',
            password='password123',
            first_name='Suresh',
            last_name='Raina',
            role='delivery_boy',
        )

        # 4. Super Admin
        self.admin_user = User.objects.create_superuser(
            username='admin_user',
            mobile_number='9999999990',
            password='adminpassword',
            role='admin',
        )

        # Address & Slot
        self.address = Address.objects.create(
            user=self.customer,
            house_number='Flat 101',
            street='Main Road',
            area='College Road',
            city='Nashik',
            state='Maharashtra',
            pincode='422001',
        )

        self.slot = DeliverySlot.objects.create(
            name='Morning (6 AM - 8 AM)',
            start_time=time(6, 0),
            end_time=time(8, 0),
        )

        self.category = Category.objects.create(name='Dairy')
        self.product = Product.objects.create(
            name='Buffalo Milk',
            category=self.category,
            price=Decimal('70.00'),
            unit='litre',
        )

    # 1. Customer creates cash order
    def test_01_customer_creates_cash_order(self):
        self.client.force_authenticate(user=self.customer)
        payload = {
            'address_id': self.address.id,
            'delivery_slot_id': self.slot.id,
            'payment_method': 'cash',
            'items': [{'product_id': self.product.id, 'quantity': 2}],
        }
        res = self.client.post('/api/v1/orders/create-order/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        order_data = res.data.get('order', {})
        self.assertEqual(order_data.get('payment_method'), 'cash')
        self.assertEqual(order_data.get('payment_status'), 'pending')
        self.assertEqual(order_data.get('status'), 'confirmed')
        self.assertNotIn('razorpay_order', res.data)

    # 2. Customer creates UPI-at-delivery order
    def test_02_customer_creates_upi_at_delivery_order(self):
        self.client.force_authenticate(user=self.customer)
        payload = {
            'address_id': self.address.id,
            'delivery_slot_id': self.slot.id,
            'payment_method': 'upi_at_delivery',
            'items': [{'product_id': self.product.id, 'quantity': 2}],
        }
        res = self.client.post('/api/v1/orders/create-order/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        order_data = res.data.get('order', {})
        self.assertEqual(order_data.get('payment_method'), 'upi_at_delivery')
        self.assertEqual(order_data.get('payment_status'), 'pending')

    # 3. Razorpay order creation still works and returns razorpay_order
    def test_03_razorpay_order_still_works(self):
        self.client.force_authenticate(user=self.customer)
        payload = {
            'address_id': self.address.id,
            'delivery_slot_id': self.slot.id,
            'payment_method': 'razorpay',
            'items': [{'product_id': self.product.id, 'quantity': 1}],
        }
        res = self.client.post('/api/v1/orders/create-order/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn('razorpay_order', res.data)
        order_data = res.data.get('order', {})
        self.assertEqual(order_data.get('payment_status'), 'pending')
        self.assertEqual(order_data.get('payment_method'), 'razorpay')

    # 4. Offline payment starts as pending
    def test_04_offline_payment_starts_as_pending(self):
        order = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('140.00'),
            final_amount=Decimal('140.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )
        self.assertEqual(order.payment_status, 'pending')

    # 5. Delivery Partner collects assigned cash order
    def test_05_delivery_partner_collects_assigned_cash_order(self):
        order = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('140.00'),
            final_amount=Decimal('140.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )
        self.client.force_authenticate(user=self.delivery_a)
        res = self.client.post(
            f'/api/v1/delivery/orders/{order.id}/collect-payment/',
            {'payment_method': 'cash'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'collected')
        self.assertEqual(order.status, 'delivered')

        collection = OfflinePaymentCollection.objects.filter(order=order).first()
        self.assertIsNotNone(collection)
        self.assertEqual(collection.amount, Decimal('140.00'))
        self.assertEqual(collection.status, 'collected')
        self.assertEqual(collection.payment_method, 'cash')

    # 6. Delivery Partner collects assigned UPI order with transaction reference
    def test_06_delivery_partner_collects_assigned_upi_order(self):
        order = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('140.00'),
            final_amount=Decimal('140.00'),
            payment_method='upi_at_delivery',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )
        self.client.force_authenticate(user=self.delivery_a)
        res = self.client.post(
            f'/api/v1/delivery/orders/{order.id}/collect-payment/',
            {
                'payment_method': 'upi_at_delivery',
                'transaction_reference': 'UPI9988776655',
            },
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'collected')

        collection = OfflinePaymentCollection.objects.filter(order=order).first()
        self.assertEqual(collection.transaction_reference, 'UPI9988776655')
        self.assertEqual(collection.payment_method, 'upi_at_delivery')

    # 7. Delivery Partner cannot collect another partner's order
    def test_07_delivery_partner_cannot_collect_unassigned_order(self):
        order = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('140.00'),
            final_amount=Decimal('140.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )
        # Authenticate as Delivery Partner B
        self.client.force_authenticate(user=self.delivery_b)
        res = self.client.post(
            f'/api/v1/delivery/orders/{order.id}/collect-payment/',
            {'payment_method': 'cash'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # 8. Customer cannot mark payment collected
    def test_08_customer_cannot_mark_payment_collected(self):
        order = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('140.00'),
            final_amount=Decimal('140.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )
        self.client.force_authenticate(user=self.customer)
        res = self.client.post(
            f'/api/v1/delivery/orders/{order.id}/collect-payment/',
            {'payment_method': 'cash'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # 9. Server determines collectible amount (frontend amount ignored)
    def test_09_backend_calculates_and_enforces_amount(self):
        order = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('140.00'),
            final_amount=Decimal('140.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )
        self.client.force_authenticate(user=self.delivery_a)
        # Attempt to pass an arbitrary tampered amount from client
        res = self.client.post(
            f'/api/v1/delivery/orders/{order.id}/collect-payment/',
            {'payment_method': 'cash', 'amount': '50.00'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        collection = OfflinePaymentCollection.objects.get(order=order)
        self.assertEqual(collection.amount, Decimal('140.00'))  # Server-calculated amount enforced

    # 10. Duplicate collection is prevented (Idempotency)
    def test_10_duplicate_collection_is_prevented(self):
        order = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('140.00'),
            final_amount=Decimal('140.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )
        self.client.force_authenticate(user=self.delivery_a)
        res1 = self.client.post(
            f'/api/v1/delivery/orders/{order.id}/collect-payment/',
            {'payment_method': 'cash'},
            format='json'
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        # Second tap
        res2 = self.client.post(
            f'/api/v1/delivery/orders/{order.id}/collect-payment/',
            {'payment_method': 'cash'},
            format='json'
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertIn("already been collected", res2.data.get("msg", ""))
        self.assertEqual(OfflinePaymentCollection.objects.filter(order=order, status='collected').count(), 1)

    # 11. Failed / unable to collect recorded
    def test_11_failed_collection_recorded(self):
        order = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('140.00'),
            final_amount=Decimal('140.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )
        self.client.force_authenticate(user=self.delivery_a)
        res = self.client.post(
            f'/api/v1/delivery/orders/{order.id}/payment-failed/',
            {'reason': 'customer_unavailable', 'notes': 'Door locked'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'pending')  # Not marked as paid
        collection = OfflinePaymentCollection.objects.filter(order=order, status='failed').first()
        self.assertIsNotNone(collection)
        self.assertEqual(collection.reason, 'customer_unavailable')

    # 12. Delivery Partner collections summary
    def test_12_delivery_partner_collections_summary(self):
        order1 = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('100.00'),
            final_amount=Decimal('100.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )
        order2 = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('150.00'),
            final_amount=Decimal('150.00'),
            payment_method='upi_at_delivery',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )
        self.client.force_authenticate(user=self.delivery_a)
        self.client.post(f'/api/v1/delivery/orders/{order1.id}/collect-payment/', {'payment_method': 'cash'})
        self.client.post(f'/api/v1/delivery/orders/{order2.id}/collect-payment/', {'payment_method': 'upi_at_delivery'})

        res = self.client.get('/api/v1/delivery/offline-collections/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        summary = res.data.get('today_summary', {})
        self.assertEqual(Decimal(summary.get('cash')), Decimal('100.00'))
        self.assertEqual(Decimal(summary.get('upi')), Decimal('150.00'))
        self.assertEqual(Decimal(summary.get('total')), Decimal('250.00'))

    # 13. Admin can view and verify offline collections
    def test_13_admin_view_and_verify_collection(self):
        order = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('140.00'),
            final_amount=Decimal('140.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )
        self.client.force_authenticate(user=self.delivery_a)
        self.client.post(f'/api/v1/delivery/orders/{order.id}/collect-payment/', {'payment_method': 'cash'})
        collection = OfflinePaymentCollection.objects.get(order=order)

        # Admin checks
        self.client.force_authenticate(user=self.admin_user)
        res_list = self.client.get('/api/v1/delivery/admin/offline-payments/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)

        res_verify = self.client.post(
            f'/api/v1/delivery/admin/offline-payments/{collection.id}/verify/',
            {'action': 'verify'},
            format='json'
        )
        self.assertEqual(res_verify.status_code, status.HTTP_200_OK)
        collection.refresh_from_db()
        self.assertEqual(collection.status, 'verified')
        self.assertEqual(collection.verified_by, self.admin_user)

    # 14. Notification failure does not rollback transaction
    @patch('notifications.services.send_push_notification')
    def test_14_notification_failure_does_not_rollback_collection(self, mock_push):
        mock_push.side_effect = Exception("FCM Service Temporarily Down")

        order = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('140.00'),
            final_amount=Decimal('140.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )
        self.client.force_authenticate(user=self.delivery_a)
        res = self.client.post(
            f'/api/v1/delivery/orders/{order.id}/collect-payment/',
            {'payment_method': 'cash'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'collected')
        self.assertEqual(OfflinePaymentCollection.objects.filter(order=order, status='collected').count(), 1)

    # 15. Customer order cancellation tests
    def test_15_customer_order_cancellation_lifecycle_and_ownership(self):
        # Create second customer for isolation check
        customer_b = User.objects.create_user(
            username='9876543219',
            mobile_number='9876543219',
            password='password123',
            role='customer',
        )

        order = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('100.00'),
            final_amount=Decimal('100.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
        )

        # A) Customer B cannot cancel Customer A's order
        self.client.force_authenticate(user=customer_b)
        res_cross = self.client.post(f'/api/v1/orders/{order.id}/cancel/')
        self.assertEqual(res_cross.status_code, status.HTTP_404_NOT_FOUND)

        # B) Customer A can cancel 'confirmed' order
        self.client.force_authenticate(user=self.customer)
        res_cancel = self.client.post(f'/api/v1/orders/{order.id}/cancel/')
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')

        # C) Already cancelled order cannot be cancelled again
        res_cancel_again = self.client.post(f'/api/v1/orders/{order.id}/cancel/')
        self.assertEqual(res_cancel_again.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_cancel_again.data.get('msg'), 'Only pending or confirmed orders can be cancelled.')

        # D) 'out_for_delivery' order cannot be cancelled
        order_ofd = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('100.00'),
            final_amount=Decimal('100.00'),
            payment_method='cash',
            payment_status='pending',
            status='out_for_delivery',
            delivery_boy=self.delivery_a,
        )
        res_ofd = self.client.post(f'/api/v1/orders/{order_ofd.id}/cancel/')
        self.assertEqual(res_ofd.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_ofd.data.get('msg'), 'Only pending or confirmed orders can be cancelled.')

        # E) 'delivered' order cannot be cancelled
        order_del = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('100.00'),
            final_amount=Decimal('100.00'),
            payment_method='cash',
            payment_status='collected',
            status='delivered',
            delivery_boy=self.delivery_a,
        )
        res_del = self.client.post(f'/api/v1/orders/{order_del.id}/cancel/')
        self.assertEqual(res_del.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_del.data.get('msg'), 'Only pending or confirmed orders can be cancelled.')

