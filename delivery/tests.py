from datetime import date, time, timedelta
from decimal import Decimal
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

    def test_accept_order_concurrency_and_single_assignment(self):
        # Create unassigned order
        unassigned_order = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('100.00'),
            final_amount=Decimal('100.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
            delivery_boy=None,
        )

        # Partner A accepts first
        self.client.force_authenticate(user=self.delivery_a)
        res_a = self.client.post(f'/api/v1/delivery/orders/{unassigned_order.id}/accept/')
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)
        self.assertEqual(res_a.data.get('order_id'), unassigned_order.id)

        # Partner B attempts to accept the same order
        self.client.force_authenticate(user=self.delivery_b)
        res_b = self.client.post(f'/api/v1/delivery/orders/{unassigned_order.id}/accept/')
        self.assertEqual(res_b.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            res_b.data.get('msg'),
            'Order has already been accepted by another delivery partner.'
        )

        # Verify order remains assigned strictly to Partner A
        unassigned_order.refresh_from_db()
        self.assertEqual(unassigned_order.delivery_boy, self.delivery_a)

        # Partner A accepting again is idempotent
        self.client.force_authenticate(user=self.delivery_a)
        res_a_again = self.client.post(f'/api/v1/delivery/orders/{unassigned_order.id}/accept/')
        self.assertEqual(res_a_again.status_code, status.HTTP_200_OK)
        self.assertEqual(res_a_again.data.get('msg'), 'You have already accepted this order.')


class DeliveryPartnerCashSummaryAndHandoverTests(APITestCase):

    def setUp(self):
        self.customer = User.objects.create_user(
            username='cust_cash',
            mobile_number='9876543299',
            password='password123',
            first_name='Rohan',
            role='customer',
        )
        self.delivery_a = User.objects.create_user(
            username='deliv_cash_a',
            mobile_number='9888881111',
            password='password123',
            first_name='Mahesh',
            role='delivery_boy',
        )
        self.delivery_b = User.objects.create_user(
            username='deliv_cash_b',
            mobile_number='9888882222',
            password='password123',
            first_name='Ganesh',
            role='delivery_boy',
        )
        self.admin = User.objects.create_user(
            username='admin_cash',
            mobile_number='9888883333',
            password='password123',
            role='admin',
            is_staff=True,
        )

        self.address = Address.objects.create(
            user=self.customer,
            house_number='12',
            street='Hub Road',
            area='Sangola',
            city='Sangola',
            state='Maharashtra',
            pincode='413307',
        )
        self.slot = DeliverySlot.objects.create(
            name='Morning Slot',
            start_time=time(6, 0),
            end_time=time(8, 0),
        )

        # Order 1 for Partner A
        self.order_1 = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('250.00'),
            final_amount=Decimal('250.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )

        # Order 2 for Partner A
        self.order_2 = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('150.00'),
            final_amount=Decimal('150.00'),
            payment_method='cash',
            payment_status='pending',
            status='confirmed',
            delivery_boy=self.delivery_a,
        )

    def test_cash_collection_and_duplicate_protection(self):
        from orders.models import OfflinePaymentCollection
        self.client.force_authenticate(user=self.delivery_a)

        # 1. Collect cash for order 1
        res = self.client.post(
            f'/api/v1/delivery/orders/{self.order_1.id}/collect-payment/',
            {'payment_method': 'cash'}
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.order_1.refresh_from_db()
        self.assertEqual(self.order_1.payment_status, 'collected')
        self.assertEqual(self.order_1.payment_method, 'cash')

        # Verify OfflinePaymentCollection created
        colls = OfflinePaymentCollection.objects.filter(order=self.order_1)
        self.assertEqual(colls.count(), 1)
        self.assertEqual(colls.first().amount, Decimal('250.00'))
        self.assertEqual(colls.first().status, 'collected')

        # 2. Duplicate cash collection attempt on the same order (safe idempotent response)
        res_dup = self.client.post(
            f'/api/v1/delivery/orders/{self.order_1.id}/collect-payment/',
            {'payment_method': 'cash'}
        )
        self.assertEqual(res_dup.status_code, status.HTTP_200_OK)
        self.assertIn('already', res_dup.data.get('msg', '').lower())
        # Ensure no duplicate collection record created
        self.assertEqual(OfflinePaymentCollection.objects.filter(order=self.order_1).count(), 1)

    def test_cash_summary_breakdown_today_and_previous_unhanded(self):
        from orders.models import OfflinePaymentCollection
        from delivery.models import CashHandover
        from django.utils import timezone
        from datetime import timedelta

        # Create past collection (yesterday): ₹300
        yesterday = timezone.now() - timedelta(days=1)
        past_order = Order.objects.create(
            user=self.customer,
            address=self.address,
            delivery_slot=self.slot,
            total_amount=Decimal('300.00'),
            final_amount=Decimal('300.00'),
            payment_method='cash',
            payment_status='collected',
            status='delivered',
            delivery_boy=self.delivery_a,
        )
        past_coll = OfflinePaymentCollection.objects.create(
            order=past_order,
            delivery_partner=self.delivery_a,
            payment_method='cash',
            amount=Decimal('300.00'),
            status='collected',
        )
        # Manually backdate collected_at
        OfflinePaymentCollection.objects.filter(pk=past_coll.pk).update(collected_at=yesterday)

        # Today's collection: ₹250
        OfflinePaymentCollection.objects.create(
            order=self.order_1,
            delivery_partner=self.delivery_a,
            payment_method='cash',
            amount=Decimal('250.00'),
            status='collected',
            collected_at=timezone.now(),
        )

        # Check cash summary before any handover
        self.client.force_authenticate(user=self.delivery_a)
        res = self.client.get('/api/v1/delivery/cash-handover/my/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        summary = res.data.get('summary', {})

        # A. Today's Cash: 250
        self.assertEqual(summary.get('today_cash'), 250.0)
        self.assertEqual(summary.get('today_order_count'), 1)
        # B. Previous Unhanded Cash: 300
        self.assertEqual(summary.get('previous_unhanded_cash'), 300.0)
        # C. Total Pending Handover: 550
        self.assertEqual(summary.get('total_pending_handover'), 550.0)
        # D. Confirmed Handovers: 0
        self.assertEqual(summary.get('confirmed_handovers'), 0.0)

        # Repeated refresh does not alter authoritative totals
        res2 = self.client.get('/api/v1/delivery/cash-handover/my/')
        self.assertEqual(res2.data.get('summary'), summary)

    def test_handover_cannot_exceed_available_balance(self):
        from orders.models import OfflinePaymentCollection
        # Collect ₹250
        OfflinePaymentCollection.objects.create(
            order=self.order_1,
            delivery_partner=self.delivery_a,
            payment_method='cash',
            amount=Decimal('250.00'),
            status='collected',
        )

        self.client.force_authenticate(user=self.delivery_a)
        # Attempt to hand over ₹300 (exceeds balance of ₹250)
        res = self.client.post(
            '/api/v1/delivery/cash-handover/submit/',
            {'submitted_amount': '300.00', 'delivery_notes': 'Too much'}
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot exceed', res.data.get('msg', ''))

        # Valid handover within balance: ₹200
        res_ok = self.client.post(
            '/api/v1/delivery/cash-handover/submit/',
            {'submitted_amount': '200.00', 'delivery_notes': 'Part 1'}
        )
        self.assertEqual(res_ok.status_code, status.HTTP_201_CREATED)

    def test_delivery_partner_isolation(self):
        from orders.models import OfflinePaymentCollection
        from delivery.models import CashHandover

        # Partner A collects ₹250
        OfflinePaymentCollection.objects.create(
            order=self.order_1,
            delivery_partner=self.delivery_a,
            payment_method='cash',
            amount=Decimal('250.00'),
            status='collected',
        )
        CashHandover.objects.create(
            delivery_boy=self.delivery_a,
            submitted_amount=Decimal('250.00'),
            status='submitted',
        )

        # Partner B views handovers
        self.client.force_authenticate(user=self.delivery_b)
        res_b = self.client.get('/api/v1/delivery/cash-handover/my/')
        self.assertEqual(res_b.status_code, status.HTTP_200_OK)

        # Partner B must have 0 cash and see no handovers belonging to Partner A
        summary_b = res_b.data.get('summary', {})
        self.assertEqual(summary_b.get('total_collected'), 0.0)
        self.assertEqual(summary_b.get('total_pending_handover'), 0.0)
        self.assertEqual(len(res_b.data.get('handovers', [])), 0)


class AdminReportsAndCashReconciliationTests(APITestCase):

    def setUp(self):
        # Admin user
        self.admin = User.objects.create_user(
            username='admin_report_tester',
            mobile_number='9876543201',
            password='password123',
            role='admin',
            is_staff=True,
        )
        # Customer
        self.customer = User.objects.create_user(
            username='cust_report_tester',
            mobile_number='9876543202',
            password='password123',
            role='customer',
        )
        # Delivery Partners
        self.partner_a = User.objects.create_user(
            username='partner_a_tester',
            mobile_number='9876543203',
            password='password123',
            first_name='Vikas',
            last_name='Shinde',
            role='delivery_boy',
        )
        self.partner_b = User.objects.create_user(
            username='partner_b_tester',
            mobile_number='9876543204',
            password='password123',
            first_name='Nitin',
            last_name='Kadam',
            role='delivery_boy',
        )

        self.address = Address.objects.create(
            user=self.customer,
            house_number='10',
            street='Station Rd',
            area='Sangola',
            city='Sangola',
            state='Maharashtra',
            pincode='413307',
        )
        self.slot = DeliverySlot.objects.create(
            name='Standard Slot',
            start_time=time(6, 0),
            end_time=time(8, 0),
        )

        from orders.models import OfflinePaymentCollection
        from delivery.models import CashHandover
        from django.utils import timezone

        self.today = timezone.localdate()
        self.yesterday = self.today - timedelta(days=1)

        # Order 1 (Today, Partner A: ₹200)
        self.order_1 = Order.objects.create(
            user=self.customer, address=self.address, delivery_slot=self.slot,
            total_amount=Decimal('200.00'), final_amount=Decimal('200.00'),
            payment_method='cash', payment_status='collected', status='delivered',
            delivery_boy=self.partner_a,
        )
        self.coll_1 = OfflinePaymentCollection.objects.create(
            order=self.order_1, delivery_partner=self.partner_a,
            payment_method='cash', amount=Decimal('200.00'), status='collected',
            collected_at=timezone.now(),
        )

        # Order 2 (Yesterday, Partner A: ₹300)
        self.order_2 = Order.objects.create(
            user=self.customer, address=self.address, delivery_slot=self.slot,
            total_amount=Decimal('300.00'), final_amount=Decimal('300.00'),
            payment_method='cash', payment_status='collected', status='delivered',
            delivery_boy=self.partner_a,
        )
        self.coll_2 = OfflinePaymentCollection.objects.create(
            order=self.order_2, delivery_partner=self.partner_a,
            payment_method='cash', amount=Decimal('300.00'), status='collected',
            collected_at=timezone.now() - timedelta(days=1),
        )
        OfflinePaymentCollection.objects.filter(pk=self.coll_2.pk).update(collected_at=timezone.now() - timedelta(days=1))

        # Order 3 (Today, Partner B: ₹150)
        self.order_3 = Order.objects.create(
            user=self.customer, address=self.address, delivery_slot=self.slot,
            total_amount=Decimal('150.00'), final_amount=Decimal('150.00'),
            payment_method='cash', payment_status='collected', status='delivered',
            delivery_boy=self.partner_b,
        )
        self.coll_3 = OfflinePaymentCollection.objects.create(
            order=self.order_3, delivery_partner=self.partner_b,
            payment_method='cash', amount=Decimal('150.00'), status='collected',
            collected_at=timezone.now(),
        )

    def test_admin_report_access_and_non_admin_denied(self):
        # 1. Unauthenticated denied (401 from DRF IsAuthenticated)
        res_anon = self.client.get('/api/admin/reports/')
        self.assertEqual(res_anon.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Non-admin customer denied (403 from admin check)
        self.client.force_authenticate(user=self.customer)
        res_cust = self.client.get('/api/admin/reports/')
        self.assertEqual(res_cust.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Non-admin delivery partner denied
        self.client.force_authenticate(user=self.partner_a)
        res_deliv = self.client.get('/api/admin/reports/')
        self.assertEqual(res_deliv.status_code, status.HTTP_403_FORBIDDEN)

        # 4. Admin allowed
        self.client.force_authenticate(user=self.admin)
        res_admin = self.client.get('/api/admin/reports/')
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        admin_data = res_admin.json()
        self.assertIn('summary', admin_data)
        self.assertIn('partner_breakdown', admin_data)

    def test_collection_summary_and_date_filtering(self):
        self.client.force_authenticate(user=self.admin)

        # Total collections across all partners: 200 + 300 + 150 = ₹650
        res_all = self.client.get('/api/admin/reports/')
        self.assertEqual(res_all.status_code, status.HTTP_200_OK)
        s_all = res_all.json()['summary']
        self.assertEqual(s_all['total_cash_collected'], 650.0)
        self.assertEqual(s_all['today_cash'], 350.0) # 200 + 150
        self.assertEqual(s_all['previous_unhanded_cash'], 300.0)
        self.assertEqual(s_all['pending_handover'], 650.0)
        self.assertEqual(s_all['orders_count'], 3)

        # Filter strictly for today
        today_str = self.today.strftime('%Y-%m-%d')
        res_today = self.client.get(f'/api/admin/reports/?start_date={today_str}&end_date={today_str}')
        s_today = res_today.json()['summary']
        self.assertEqual(s_today['total_cash_collected'], 350.0)
        self.assertEqual(s_today['orders_count'], 2)

        # Filter strictly for yesterday
        yesterday_str = self.yesterday.strftime('%Y-%m-%d')
        res_yest = self.client.get(f'/api/admin/reports/?start_date={yesterday_str}&end_date={yesterday_str}')
        s_yest = res_yest.json()['summary']
        self.assertEqual(s_yest['total_cash_collected'], 300.0)
        self.assertEqual(s_yest['orders_count'], 1)

    def test_partner_filtering_and_breakdown(self):
        self.client.force_authenticate(user=self.admin)

        # Filter by Partner A
        res_a = self.client.get(f'/api/admin/reports/?delivery_boy_id={self.partner_a.id}')
        data_a = res_a.json()
        s_a = data_a['summary']
        self.assertEqual(s_a['total_cash_collected'], 500.0) # 200 + 300
        self.assertEqual(s_a['orders_count'], 2)

        # Breakdown table has Partner A
        breakdown = data_a['partner_breakdown']
        self.assertEqual(len(breakdown), 1)
        self.assertEqual(breakdown[0]['id'], self.partner_a.id)
        self.assertEqual(breakdown[0]['cash_collected'], 500.0)

    def test_cash_handover_reconciliation_flow_and_duplicate_protection(self):
        from delivery.models import CashHandover
        # Partner A submits handover of ₹400
        handover = CashHandover.objects.create(
            delivery_boy=self.partner_a,
            submitted_amount=Decimal('400.00'),
            status='submitted',
            delivery_notes='Collected from rounds',
        )

        self.client.force_authenticate(user=self.admin)

        # 1. Attempt confirming more than partner's collected cash (Partner A has ₹500, attempt ₹600)
        res_exceed = self.client.post(
            f'/api/admin/cash-handovers/{handover.id}/confirm/',
            {'received_amount': '600.00'},
            format='json'
        )
        self.assertEqual(res_exceed.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('exceeds', res_exceed.json().get('error', ''))

        # 2. Valid Admin confirmation: exactly ₹400 received
        res_confirm = self.client.post(
            f'/api/admin/cash-handovers/{handover.id}/confirm/',
            {'received_amount': '400.00', 'admin_notes': 'Physical notes verified'},
            format='json'
        )
        self.assertEqual(res_confirm.status_code, status.HTTP_200_OK)
        handover.refresh_from_db()
        self.assertEqual(handover.status, 'confirmed')
        self.assertEqual(handover.received_amount, Decimal('400.00'))

        # 3. Duplicate confirmation attempt on already confirmed handover is rejected
        res_dup = self.client.post(
            f'/api/admin/cash-handovers/{handover.id}/confirm/',
            {'received_amount': '400.00'},
            format='json'
        )
        self.assertEqual(res_dup.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already been confirmed', res_dup.json().get('error', ''))

        # 4. Check updated report metrics after handover
        res_report = self.client.get('/api/admin/reports/')
        s_rep = res_report.json()['summary']
        self.assertEqual(s_rep['total_cash_collected'], 650.0)
        self.assertEqual(s_rep['confirmed_cash'], 400.0)
        self.assertEqual(s_rep['pending_handover'], 250.0) # 650 - 400



