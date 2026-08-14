from datetime import date, time, timedelta
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

from accounts.models import Address
from orders.models import Order, OrderItem, DeliverySlot
from products.models import Category, Product
from subscriptions.models import Subscription
from delivery.models import DailyDelivery

User = get_user_model()


class DeliveryPartnerSecurityAndDataMinimizationTests(APITestCase):

    def setUp(self):
        # Create Customer
        self.customer = User.objects.create_user(
            username='customer_user',
            mobile_number='9876543210',
            password='password123',
            first_name='Rahul',
            last_name='Patil',
            role='customer',
        )

        # Create Delivery Partner A
        self.delivery_a = User.objects.create_user(
            username='delivery_a',
            mobile_number='9998887771',
            password='password123',
            first_name='Amit',
            last_name='Kumar',
            role='delivery_boy',
        )

        # Create Delivery Partner B
        self.delivery_b = User.objects.create_user(
            username='delivery_b',
            mobile_number='9998887772',
            password='password123',
            first_name='Suresh',
            last_name='Raina',
            role='delivery_boy',
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
            latitude=20.0059,
            longitude=73.7997,
        )

        self.slot = DeliverySlot.objects.create(
            name='Morning (6 AM - 8 AM)',
            start_time=time(6, 0),
            end_time=time(8, 0),
        )

        self.category = Category.objects.create(name='Milk')
        self.product = Product.objects.create(
            name='Buffalo Milk',
            category=self.category,
            price=70,
            unit='litre',
        )

        # Order assigned to Delivery Partner A
        self.order_a = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=140,
            final_amount=140,
            status='confirmed',
            delivery_boy=self.delivery_a,
        )
        OrderItem.objects.create(
            order=self.order_a,
            product=self.product,
            quantity=2,
            price=70,
        )

        # Subscription & Daily Delivery assigned to Delivery Partner A
        self.subscription_a = Subscription.objects.create(
            user=self.customer,
            product=self.product,
            address=self.address,
            delivery_slot=self.slot,
            quantity=2,
            price_per_unit=70,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            status='active',
        )
        self.daily_delivery_a = DailyDelivery.objects.create(
            subscription=self.subscription_a,
            delivery_boy=self.delivery_a,
            delivery_date=date.today(),
            status='pending',
        )

    def test_customer_forbidden_from_delivery_endpoints(self):
        self.client.force_authenticate(user=self.customer)
        res1 = self.client.get('/api/v1/delivery/my-orders/')
        self.assertEqual(res1.status_code, status.HTTP_403_FORBIDDEN)

        res2 = self.client.get('/api/v1/delivery/my-subscriptions/')
        self.assertEqual(res2.status_code, status.HTTP_403_FORBIDDEN)

    def test_delivery_partner_data_minimization(self):
        self.client.force_authenticate(user=self.delivery_a)

        res = self.client.get('/api/v1/delivery/my-orders/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        orders = res.data.get('orders', [])
        self.assertEqual(len(orders), 1)

        order_data = orders[0]
        # Verify minimal customer fields
        customer_info = order_data.get('customer', {})
        self.assertIn('name', customer_info)
        self.assertIn('mobile_number', customer_info)
        self.assertNotIn('password', customer_info)
        self.assertNotIn('wallet_balance', customer_info)

        # Verify minimal address fields
        addr_info = order_data.get('delivery_address', {})
        self.assertEqual(addr_info['house_number'], 'Flat 101')
        self.assertEqual(addr_info['city'], 'Nashik')

    def test_unassigned_order_ownership_forbidden(self):
        # Authenticate as Delivery Partner B
        self.client.force_authenticate(user=self.delivery_b)

        # Attempt GET order_a (assigned to A)
        res_get = self.client.get(f'/api/v1/delivery/orders/{self.order_a.id}/')
        self.assertEqual(res_get.status_code, status.HTTP_403_FORBIDDEN)

        # Attempt POST update-status on order_a (assigned to A)
        res_post = self.client.post(
            f'/api/v1/delivery/orders/{self.order_a.id}/update-status/',
            {'status': 'out_for_delivery'}
        )
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)

    def test_status_transition_validation(self):
        self.client.force_authenticate(user=self.delivery_a)

        # Invalid transition: confirmed directly to delivered (expects out_for_delivery first)
        res_invalid = self.client.post(
            f'/api/v1/delivery/orders/{self.order_a.id}/update-status/',
            {'status': 'delivered'}
        )
        self.assertEqual(res_invalid.status_code, status.HTTP_400_BAD_REQUEST)

        # Valid transition: confirmed -> out_for_delivery
        res_out = self.client.post(
            f'/api/v1/delivery/orders/{self.order_a.id}/update-status/',
            {'status': 'out_for_delivery'}
        )
        self.assertEqual(res_out.status_code, status.HTTP_200_OK)

        # Valid transition: out_for_delivery -> delivered
        res_del = self.client.post(
            f'/api/v1/delivery/orders/{self.order_a.id}/update-status/',
            {'status': 'delivered'}
        )
        self.assertEqual(res_del.status_code, status.HTTP_200_OK)
