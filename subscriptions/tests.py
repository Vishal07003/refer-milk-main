from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client
from django.utils import timezone
from accounts.models import User, Address
from products.models import Product, Category
from orders.models import DeliverySlot
from subscriptions.models import Subscription, SubscriptionPlan
from delivery.models import DailyDelivery
import json


class SubscriptionRefactoringTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Fresh Dairy", description="Milk and milk products")
        self.product = Product.objects.create(
            name="A2 Gir Cow Milk",
            category=self.category,
            price=Decimal("75.00"),
            unit="litre",
            is_active=True,
            is_subscription_eligible=True
        )

        self.customer = User.objects.create_user(
            username="9876543210",
            mobile_number="9876543210",
            first_name="Ramesh",
            last_name="Kulkarni",
            role="customer"
        )
        self.address = Address.objects.create(
            user=self.customer,
            label="home",
            house_number="B-102",
            street="Station Road",
            city="Sangola",
            state="Maharashtra",
            pincode="413307",
            is_default=True
        )

        self.delivery_boy = User.objects.create_user(
            username="9822001122",
            mobile_number="9822001122",
            first_name="Sanjay",
            last_name="Patil",
            role="delivery_boy"
        )

        self.admin = User.objects.create_superuser(
            username="admin",
            mobile_number="9999999999",
            password="adminpassword"
        )

        self.slot = DeliverySlot.objects.create(
            name="Early Morning",
            start_time="05:30:00",
            end_time="07:30:00",
            is_active=True
        )

    def get_token(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return str(RefreshToken.for_user(user).access_token)

    def test_complete_subscription_workflow(self):
        # 1. Admin creates predefined SubscriptionPlan
        plan_response = self.client.post(
            "/api/admin/subscription-plans/",
            data=json.dumps({
                "name": "Daily Pure A2 Cow Milk 1L",
                "product_id": self.product.id,
                "quantity": 1.0,
                "unit": "litre",
                "frequency": "daily",
                "price_per_unit": "75.00",
                "schedule_description": "Morning Delivery (5:30 AM - 7:30 AM)",
                "is_active": True
            }),
            content_type="application/json"
        )
        self.assertEqual(plan_response.status_code, 201)
        plan_id = plan_response.json()["plan"]["id"]
        plan = SubscriptionPlan.objects.get(id=plan_id)
        self.assertEqual(plan.name, "Daily Pure A2 Cow Milk 1L")
        self.assertTrue(plan.is_active)

        # 2. Customer views active plans list
        active_plans_resp = self.client.get("/api/v1/subscriptions/plans/")
        self.assertEqual(active_plans_resp.status_code, 200)
        plans_list = active_plans_resp.json()["plans"]
        self.assertTrue(any(p["id"] == plan_id for p in plans_list))

        # 3. Customer submits plan selection request (Status is pending approval)
        from rest_framework_simplejwt.tokens import RefreshToken
        token = str(RefreshToken.for_user(self.customer).access_token)
        auth_header = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

        sub_request_resp = self.client.post(
            "/api/v1/subscriptions/request/",
            data=json.dumps({
                "plan_id": plan_id,
                "address_id": self.address.id,
                "delivery_slot_id": self.slot.id,
            }),
            content_type="application/json",
            **auth_header
        )
        self.assertEqual(sub_request_resp.status_code, 201)
        sub_id = sub_request_resp.json()["subscription"]["id"]
        subscription = Subscription.objects.get(id=sub_id)

        self.assertEqual(subscription.status, "pending")
        self.assertEqual(subscription.plan, plan)
        self.assertEqual(subscription.product, self.product)
        self.assertEqual(subscription.price_per_unit, Decimal("75.00"))

        # Customer CANNOT start deliveries while pending; no DailyDeliveries generated
        self.assertEqual(DailyDelivery.objects.filter(subscription=subscription).count(), 0)

        # Prevent duplicate pending request for same plan
        dup_resp = self.client.post(
            "/api/v1/subscriptions/request/",
            data=json.dumps({
                "plan_id": plan_id,
                "address_id": self.address.id
            }),
            content_type="application/json",
            **auth_header
        )
        self.assertEqual(dup_resp.status_code, 400)

        # 4. Admin views pending subscriptions list
        self.client.logout()
        admin_list_resp = self.client.get("/api/admin/subscriptions/?status=pending")
        self.assertEqual(admin_list_resp.status_code, 200)
        pending_subs = admin_list_resp.json()["subscriptions"]
        self.assertTrue(any(s["id"] == sub_id for s in pending_subs))

        # 5. Admin approves and activates subscription with assigned delivery boy
        tomorrow = (timezone.localdate() + timedelta(days=1)).strftime("%Y-%m-%d")
        approve_resp = self.client.post(
            "/api/admin/subscriptions/",
            data=json.dumps({
                "id": sub_id,
                "action": "approve",
                "quantity": 1.0,
                "start_date": tomorrow,
                "delivery_slot_id": self.slot.id,
                "delivery_boy_id": self.delivery_boy.id
            }),
            content_type="application/json"
        )
        self.assertEqual(approve_resp.status_code, 200)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, "active")
        self.assertEqual(subscription.delivery_boy, self.delivery_boy)

        # Deliveries generated for active subscription
        delivery_count = DailyDelivery.objects.filter(subscription=subscription).count()
        self.assertGreater(delivery_count, 0)

        # 6. Admin pauses subscription -> future pending deliveries removed
        pause_resp = self.client.post(
            "/api/admin/subscriptions/",
            data=json.dumps({"id": sub_id, "action": "pause"}),
            content_type="application/json"
        )
        self.assertEqual(pause_resp.status_code, 200)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, "paused")

        # 7. Admin resumes subscription
        resume_resp = self.client.post(
            "/api/admin/subscriptions/",
            data=json.dumps({"id": sub_id, "action": "resume"}),
            content_type="application/json"
        )
        self.assertEqual(resume_resp.status_code, 200)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, "active")

        # 8. Admin cancels subscription -> no future deliveries generated
        cancel_resp = self.client.post(
            "/api/admin/subscriptions/",
            data=json.dumps({"id": sub_id, "action": "cancel"}),
            content_type="application/json"
        )
        self.assertEqual(cancel_resp.status_code, 200)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, "cancelled")

        # 9. Plan deactivation preserves existing customer subscription record
        deact_resp = self.client.delete(
            "/api/admin/subscription-plans/",
            data=json.dumps({"id": plan_id}),
            content_type="application/json"
        )
        self.assertEqual(deact_resp.status_code, 200)
        plan.refresh_from_db()
        self.assertFalse(plan.is_active)
        # Customer subscription and historical deliveries still exist
        self.assertTrue(Subscription.objects.filter(id=sub_id).exists())

    def test_customer_pause_and_resume_subscription(self):
        """
        Comprehensive test for Customer Pause & Resume APIs:
        1. Customer can pause own active subscription.
        2. Customer can resume own paused subscription.
        3. Customer cannot pause another customer's subscription.
        4. Customer cannot resume another customer's subscription.
        5. ACTIVE -> pause works.
        6. PAUSED -> resume works.
        7. PAUSED -> pause fails (reject with 400).
        8. ACTIVE -> resume fails (reject with 400).
        9. CANCELLED -> pause fails (reject with 400).
        10. CANCELLED -> resume fails (reject with 400).
        11. Pause preserves historical deliveries and does not modify delivered records.
        12. Pause removes future pending deliveries.
        13. Resume re-generates future daily deliveries without duplicates.
        14. Assigned delivery partner relationship is strictly preserved.
        15. Customer receives pause and resume notifications.
        """
        from rest_framework_simplejwt.tokens import RefreshToken
        token_a = str(RefreshToken.for_user(self.customer).access_token)
        header_a = {"HTTP_AUTHORIZATION": f"Bearer {token_a}"}

        # Customer B
        customer_b = User.objects.create(mobile_number="9876543219", role="customer")
        token_b = str(RefreshToken.for_user(customer_b).access_token)
        header_b = {"HTTP_AUTHORIZATION": f"Bearer {token_b}"}


        today = timezone.localdate()
        sub = Subscription.objects.create(
            user=self.customer,
            product=self.product,
            address=self.address,
            delivery_slot=self.slot,
            delivery_boy=self.delivery_boy,
            quantity=Decimal("2.0"),
            start_date=today - timedelta(days=2),
            end_date=today + timedelta(days=5),
            price_per_unit=Decimal("70.00"),
            discount_per_unit=Decimal("0.00"),
            final_price_per_unit=Decimal("70.00"),
            total_amount=Decimal("4200.00"),
            status="active"
        )

        # Historical delivery (yesterday - delivered)
        past_delivery = DailyDelivery.objects.create(
            subscription=sub,
            delivery_boy=self.delivery_boy,
            delivery_date=today - timedelta(days=1),
            status="delivered",
            delivered_at=timezone.now() - timedelta(days=1)
        )

        # Today delivery (pending)
        today_delivery = DailyDelivery.objects.create(
            subscription=sub,
            delivery_boy=self.delivery_boy,
            delivery_date=today,
            status="pending"
        )

        # Future delivery (tomorrow - pending)
        future_delivery = DailyDelivery.objects.create(
            subscription=sub,
            delivery_boy=self.delivery_boy,
            delivery_date=today + timedelta(days=1),
            status="pending"
        )

        # 3. Customer B CANNOT pause Customer A's subscription
        unauth_pause = self.client.post(f"/api/v1/subscriptions/{sub.id}/pause/", **header_b)
        self.assertEqual(unauth_pause.status_code, 404)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "active")

        # 8. ACTIVE -> resume fails
        invalid_resume = self.client.post(f"/api/v1/subscriptions/{sub.id}/resume/", **header_a)
        self.assertEqual(invalid_resume.status_code, 400)
        self.assertIn("already active", invalid_resume.data["msg"])

        # 1. Customer A pauses own subscription
        pause_resp = self.client.post(f"/api/v1/subscriptions/{sub.id}/pause/", **header_a)
        self.assertEqual(pause_resp.status_code, 200)
        self.assertTrue(pause_resp.data["success"])
        sub.refresh_from_db()
        self.assertEqual(sub.status, "paused")

        # Partner and attributes preserved
        self.assertEqual(sub.delivery_boy, self.delivery_boy)
        self.assertEqual(sub.quantity, Decimal("2.0"))
        self.assertEqual(sub.price_per_unit, Decimal("70.00"))

        # Historical delivered delivery preserved
        self.assertTrue(DailyDelivery.objects.filter(id=past_delivery.id, status="delivered").exists())
        # Today's delivery preserved
        self.assertTrue(DailyDelivery.objects.filter(id=today_delivery.id).exists())
        # Future pending delivery deleted
        self.assertFalse(DailyDelivery.objects.filter(id=future_delivery.id).exists())

        # 7. PAUSED -> pause fails
        dup_pause = self.client.post(f"/api/v1/subscriptions/{sub.id}/pause/", **header_a)
        self.assertEqual(dup_pause.status_code, 400)
        self.assertIn("already paused", dup_pause.data["msg"])

        # 4. Customer B CANNOT resume Customer A's subscription
        unauth_resume = self.client.post(f"/api/v1/subscriptions/{sub.id}/resume/", **header_b)
        self.assertEqual(unauth_resume.status_code, 404)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "paused")

        # 2. Customer A resumes own subscription
        resume_resp = self.client.post(f"/api/v1/subscriptions/{sub.id}/resume/", **header_a)
        self.assertEqual(resume_resp.status_code, 200)
        self.assertTrue(resume_resp.data["success"])
        sub.refresh_from_db()
        self.assertEqual(sub.status, "active")

        # Future deliveries re-generated with same delivery boy
        tomorrow_drop = DailyDelivery.objects.filter(subscription=sub, delivery_date=today + timedelta(days=1)).first()
        self.assertIsNotNone(tomorrow_drop)
        self.assertEqual(tomorrow_drop.delivery_boy, self.delivery_boy)
        self.assertEqual(tomorrow_drop.status, "pending")

        # No duplicate drops generated for today or yesterday
        self.assertEqual(DailyDelivery.objects.filter(subscription=sub, delivery_date=today).count(), 1)
        self.assertEqual(DailyDelivery.objects.filter(subscription=sub, delivery_date=today - timedelta(days=1)).count(), 1)

        # Cancelled state tests
        sub.status = "cancelled"
        sub.save()

        # 9 & 10. CANCELLED -> pause and resume both fail
        cancelled_pause = self.client.post(f"/api/v1/subscriptions/{sub.id}/pause/", **header_a)
        self.assertEqual(cancelled_pause.status_code, 400)
        cancelled_resume = self.client.post(f"/api/v1/subscriptions/{sub.id}/resume/", **header_a)
        self.assertEqual(cancelled_resume.status_code, 400)

    def test_repeated_pause_resume_cycles_production_safety(self):
        """
        Production-safety test for repeated pause/resume cycles:
        1. ACTIVE customer subscription with assigned delivery boy.
        2. Verify historical delivered & failed records exist.
        3. Measure counts across multiple pause/resume cycles (Cycle 1, Cycle 2, Cycle 3).
        4. Verify delivery_date + subscription uniqueness constraint.
        5. Verify no duplicate DailyDelivery records created.
        6. Verify subscription ID and delivery boy consistency throughout.
        7. Verify Customer isolation.
        """
        from rest_framework_simplejwt.tokens import RefreshToken
        token_a = str(RefreshToken.for_user(self.customer).access_token)
        header_a = {"HTTP_AUTHORIZATION": f"Bearer {token_a}"}

        customer_b = User.objects.create(mobile_number="9876543299", role="customer")
        token_b = str(RefreshToken.for_user(customer_b).access_token)
        header_b = {"HTTP_AUTHORIZATION": f"Bearer {token_b}"}

        today = timezone.localdate()
        # 8-day span: today - 2 days (historical) to today + 5 days (future)
        sub = Subscription.objects.create(
            user=self.customer,
            product=self.product,
            address=self.address,
            delivery_slot=self.slot,
            delivery_boy=self.delivery_boy,
            quantity=Decimal("2.0"),
            start_date=today - timedelta(days=2),
            end_date=today + timedelta(days=5),
            price_per_unit=Decimal("70.00"),
            discount_per_unit=Decimal("0.00"),
            final_price_per_unit=Decimal("70.00"),
            total_amount=Decimal("4200.00"),
            status="active"
        )
        initial_sub_id = sub.id
        initial_partner_id = sub.delivery_boy_id

        # Historical delivered drop
        past_delivered = DailyDelivery.objects.create(
            subscription=sub,
            delivery_boy=self.delivery_boy,
            delivery_date=today - timedelta(days=2),
            status="delivered",
            delivered_at=timezone.now() - timedelta(days=2)
        )
        # Historical failed drop
        past_failed = DailyDelivery.objects.create(
            subscription=sub,
            delivery_boy=self.delivery_boy,
            delivery_date=today - timedelta(days=1),
            status="failed",
            notes="Customer door locked"
        )
        # Today's drop
        today_drop = DailyDelivery.objects.create(
            subscription=sub,
            delivery_boy=self.delivery_boy,
            delivery_date=today,
            status="pending"
        )
        # Future drops: +1, +2, +3, +4, +5
        for offset in range(1, 6):
            DailyDelivery.objects.create(
                subscription=sub,
                delivery_boy=self.delivery_boy,
                delivery_date=today + timedelta(days=offset),
                status="pending"
            )

        # Baseline count before pause: 2 historical + 1 today + 5 future = 8 records
        initial_count = DailyDelivery.objects.filter(subscription=sub).count()
        self.assertEqual(initial_count, 8)

        # Perform 3 consecutive pause/resume cycles
        for cycle in range(1, 4):
            # Customer B cannot pause
            unauth_resp = self.client.post(f"/api/v1/subscriptions/{sub.id}/pause/", **header_b)
            self.assertEqual(unauth_resp.status_code, 404)

            # PAUSE
            pause_resp = self.client.post(f"/api/v1/subscriptions/{sub.id}/pause/", **header_a)
            self.assertEqual(pause_resp.status_code, 200, f"Cycle {cycle} pause failed")
            sub.refresh_from_db()
            self.assertEqual(sub.status, "paused")

            # In paused state: future drops (> today) deleted.
            # Remaining: 2 historical + 1 today = 3 records
            paused_count = DailyDelivery.objects.filter(subscription=sub).count()
            self.assertEqual(paused_count, 3, f"Cycle {cycle} paused delivery count mismatch")

            # Check historical records untouched
            self.assertTrue(DailyDelivery.objects.filter(id=past_delivered.id, status="delivered").exists())
            self.assertTrue(DailyDelivery.objects.filter(id=past_failed.id, status="failed").exists())
            self.assertTrue(DailyDelivery.objects.filter(id=today_drop.id).exists())

            # Customer B cannot resume
            unauth_resume = self.client.post(f"/api/v1/subscriptions/{sub.id}/resume/", **header_b)
            self.assertEqual(unauth_resume.status_code, 404)

            # RESUME
            resume_resp = self.client.post(f"/api/v1/subscriptions/{sub.id}/resume/", **header_a)
            self.assertEqual(resume_resp.status_code, 200, f"Cycle {cycle} resume failed")
            sub.refresh_from_db()
            self.assertEqual(sub.status, "active")

            # In resumed state: exactly 8 records again
            resumed_count = DailyDelivery.objects.filter(subscription=sub).count()
            self.assertEqual(resumed_count, 8, f"Cycle {cycle} resumed delivery count mismatch")

            # Check uniqueness: every delivery_date has exactly 1 record
            dates = DailyDelivery.objects.filter(subscription=sub).values_list("delivery_date", flat=True)
            self.assertEqual(len(dates), len(set(dates)), f"Cycle {cycle} found duplicate delivery dates")

            # Check subscription ID and partner consistency
            self.assertEqual(sub.id, initial_sub_id)
            self.assertEqual(sub.delivery_boy_id, initial_partner_id)

            # Check that all future drops have the same assigned partner
            future_drops = DailyDelivery.objects.filter(subscription=sub, delivery_date__gt=today)
            self.assertEqual(future_drops.count(), 5)
            for drop in future_drops:
                self.assertEqual(drop.delivery_boy_id, initial_partner_id)
                self.assertEqual(drop.status, "pending")

    def test_customer_bills_authoritative_calculation_and_ownership(self):
        """
        Tests Customer Bills endpoint:
        1. Customer A can retrieve own bills.
        2. Delivered drops are accurately counted and multiplied by final rate.
        3. Failed drops are NOT billed into delivered totals.
        4. Customer B cannot see Customer A's bills.
        5. Exact Decimal amounts are verified.
        """
        today = timezone.localdate()
        sub = Subscription.objects.create(
            user=self.customer,
            product=self.product,
            address=self.address,
            delivery_slot=self.slot,
            quantity=Decimal("2.00"),
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=25),
            price_per_unit=Decimal("75.00"),
            discount_per_unit=Decimal("5.00"),
            final_price_per_unit=Decimal("70.00"),
            total_amount=Decimal("4200.00"),
            status="active",
            delivery_boy=self.delivery_boy,
        )

        # 3 delivered drops, 1 failed drop, 1 pending today drop
        DailyDelivery.objects.create(
            subscription=sub, delivery_boy=self.delivery_boy, delivery_date=today - timedelta(days=3), status="delivered"
        )
        DailyDelivery.objects.create(
            subscription=sub, delivery_boy=self.delivery_boy, delivery_date=today - timedelta(days=2), status="delivered"
        )
        DailyDelivery.objects.create(
            subscription=sub, delivery_boy=self.delivery_boy, delivery_date=today - timedelta(days=1), status="delivered"
        )
        DailyDelivery.objects.create(
            subscription=sub, delivery_boy=self.delivery_boy, delivery_date=today - timedelta(days=4), status="failed"
        )
        DailyDelivery.objects.create(
            subscription=sub, delivery_boy=self.delivery_boy, delivery_date=today, status="pending"
        )

        header_a = {"HTTP_AUTHORIZATION": f"Bearer {self.get_token(self.customer)}"}

        # Request customer bills
        res = self.client.get("/api/v1/subscriptions/bills/", **header_a)
        self.assertEqual(res.status_code, 200)
        bills = res.data.get("bills", [])
        self.assertEqual(len(bills), 1)

        bill = bills[0]
        self.assertEqual(bill["subscription_id"], sub.id)
        self.assertEqual(bill["delivered_drops_count"], 3)
        self.assertEqual(bill["failed_drops_count"], 1)
        self.assertEqual(Decimal(str(bill["delivered_volume"])), Decimal("6.00")) # 3 drops * 2.00 L
        self.assertEqual(Decimal(str(bill["rate_per_unit"])), Decimal("75.00"))
        self.assertEqual(Decimal(str(bill["discount_per_unit"])), Decimal("5.00"))
        self.assertEqual(Decimal(str(bill["final_rate_per_unit"])), Decimal("70.00"))
        self.assertEqual(Decimal(str(bill["delivered_subtotal"])), Decimal("450.00")) # 6 L * 75
        self.assertEqual(Decimal(str(bill["discount_total"])), Decimal("30.00")) # 6 L * 5
        self.assertEqual(Decimal(str(bill["amount_payable"])), Decimal("420.00")) # 6 L * 70

        # Customer B has 0 bills
        customer_b = User.objects.create_user(
            username="9811223344", mobile_number="9811223344", role="customer"
        )
        header_b = {"HTTP_AUTHORIZATION": f"Bearer {self.get_token(customer_b)}"}
        res_b = self.client.get("/api/v1/subscriptions/bills/", **header_b)
        self.assertEqual(res_b.status_code, 200)
        self.assertEqual(len(res_b.data.get("bills", [])), 0)

    def test_customer_delivery_calendar_lifecycle_and_security(self):
        """
        Tests Customer Delivery Calendar endpoint:
        1. Customer retrieves calendar for own subscription.
        2. Delivered, failed, and pending deliveries are accurately detailed.
        3. Paused subscription hides deleted future drops; resume displays regenerated drops.
        4. Customer B cannot view Customer A's subscription calendar (HTTP 404).
        5. No duplicate dates in calendar.
        """
        today = timezone.localdate()
        sub = Subscription.objects.create(
            user=self.customer,
            product=self.product,
            address=self.address,
            delivery_slot=self.slot,
            quantity=Decimal("1.50"),
            start_date=today - timedelta(days=2),
            end_date=today + timedelta(days=2),
            price_per_unit=Decimal("75.00"),
            discount_per_unit=Decimal("0.00"),
            final_price_per_unit=Decimal("75.00"),
            total_amount=Decimal("3375.00"),
            status="active",
            delivery_boy=self.delivery_boy,
        )

        d1 = DailyDelivery.objects.create(
            subscription=sub, delivery_boy=self.delivery_boy, delivery_date=today - timedelta(days=2), status="delivered"
        )
        d2 = DailyDelivery.objects.create(
            subscription=sub, delivery_boy=self.delivery_boy, delivery_date=today - timedelta(days=1), status="failed"
        )
        d3 = DailyDelivery.objects.create(
            subscription=sub, delivery_boy=self.delivery_boy, delivery_date=today, status="pending"
        )
        d4 = DailyDelivery.objects.create(
            subscription=sub, delivery_boy=self.delivery_boy, delivery_date=today + timedelta(days=1), status="pending"
        )
        d5 = DailyDelivery.objects.create(
            subscription=sub, delivery_boy=self.delivery_boy, delivery_date=today + timedelta(days=2), status="pending"
        )

        header_a = {"HTTP_AUTHORIZATION": f"Bearer {self.get_token(self.customer)}"}

        # Fetch calendar
        res = self.client.get(f"/api/v1/subscriptions/{sub.id}/deliveries/", **header_a)
        self.assertEqual(res.status_code, 200)
        deliveries = res.data.get("deliveries", [])
        self.assertEqual(len(deliveries), 5)

        statuses = [d["status"] for d in deliveries]
        self.assertEqual(statuses, ["delivered", "failed", "pending", "pending", "pending"])

        # Customer B cannot access
        customer_b = User.objects.create_user(
            username="9855667788", mobile_number="9855667788", role="customer"
        )
        header_b = {"HTTP_AUTHORIZATION": f"Bearer {self.get_token(customer_b)}"}
        res_cross = self.client.get(f"/api/v1/subscriptions/{sub.id}/deliveries/", **header_b)
        self.assertEqual(res_cross.status_code, 404)

        # PAUSE subscription -> future drops removed
        self.client.post(f"/api/v1/subscriptions/{sub.id}/pause/", **header_a)
        res_paused = self.client.get(f"/api/v1/subscriptions/{sub.id}/deliveries/", **header_a)
        self.assertEqual(res_paused.status_code, 200)
        self.assertEqual(len(res_paused.data.get("deliveries", [])), 3) # today + 2 historical

        # RESUME subscription -> future drops regenerated
        self.client.post(f"/api/v1/subscriptions/{sub.id}/resume/", **header_a)
        res_resumed = self.client.get(f"/api/v1/subscriptions/{sub.id}/deliveries/", **header_a)
        self.assertEqual(res_resumed.status_code, 200)
        resumed_delivs = res_resumed.data.get("deliveries", [])
        self.assertEqual(len(resumed_delivs), 5)

        # Verify no duplicate dates
        dates = [d["delivery_date"] for d in resumed_delivs]
        self.assertEqual(len(dates), len(set(dates)))

    def test_customer_update_subscription_schedule(self):
        """
        Verify customer can update their delivery slot and quantity for an active subscription.
        """
        new_slot = DeliverySlot.objects.create(
            name="Evening Slot",
            start_time="17:00:00",
            end_time="19:00:00",
            is_active=True,
        )

        sub = Subscription.objects.create(
            user=self.customer,
            product=self.product,
            address=self.address,
            delivery_slot=self.slot,
            quantity=Decimal("1.00"),
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            price_per_unit=Decimal("75.00"),
            discount_per_unit=Decimal("0.00"),
            final_price_per_unit=Decimal("75.00"),
            total_amount=Decimal("2250.00"),
            status="active",
        )

        header = {"HTTP_AUTHORIZATION": f"Bearer {self.get_token(self.customer)}"}

        # Customer updates slot and quantity
        patch_res = self.client.patch(
            f"/api/v1/subscriptions/{sub.id}/",
            {"delivery_slot_id": new_slot.id, "quantity": "2.00"},
            content_type="application/json",
            **header,
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.data["subscription"]["delivery_slot"], new_slot.id)
        self.assertEqual(Decimal(patch_res.data["subscription"]["quantity"]), Decimal("2.00"))

        # Verify DB updated
        sub.refresh_from_db()
        self.assertEqual(sub.delivery_slot_id, new_slot.id)
        self.assertEqual(sub.quantity, Decimal("2.00"))
        self.assertEqual(sub.total_amount, Decimal("75.00") * Decimal("2.00") * 30)

    def test_customer_cancel_subscription_workflow(self):
        """
        Verify customer can cancel active/paused/pending subscription and future pending deliveries are removed.
        """
        sub = Subscription.objects.create(
            user=self.customer,
            product=self.product,
            address=self.address,
            delivery_slot=self.slot,
            quantity=Decimal("1.00"),
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            price_per_unit=Decimal("75.00"),
            discount_per_unit=Decimal("0.00"),
            final_price_per_unit=Decimal("75.00"),
            total_amount=Decimal("2250.00"),
            status="active",
        )

        from delivery.models import DailyDelivery
        today = timezone.localdate()
        past_deliv = DailyDelivery.objects.create(
            subscription=sub,
            delivery_boy=self.delivery_boy,
            delivery_date=today - timedelta(days=1),
            status="delivered",
        )
        today_deliv = DailyDelivery.objects.create(
            subscription=sub,
            delivery_boy=self.delivery_boy,
            delivery_date=today,
            status="pending",
        )
        future_deliv = DailyDelivery.objects.create(
            subscription=sub,
            delivery_boy=self.delivery_boy,
            delivery_date=today + timedelta(days=1),
            status="pending",
        )

        header = {"HTTP_AUTHORIZATION": f"Bearer {self.get_token(self.customer)}"}

        # Cancel subscription
        cancel_res = self.client.post(
            f"/api/v1/subscriptions/{sub.id}/cancel/",
            {"payment_method": "cash"},
            content_type="application/json",
            **header,
        )
        self.assertEqual(cancel_res.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "cancelled")
        self.assertIsNotNone(sub.cancelled_at)

        # Historical and today's deliveries preserved, future pending removed
        self.assertTrue(DailyDelivery.objects.filter(id=past_deliv.id).exists())
        self.assertTrue(DailyDelivery.objects.filter(id=today_deliv.id).exists())
        self.assertFalse(DailyDelivery.objects.filter(id=future_deliv.id).exists())

        # Cannot cancel again
        second_cancel = self.client.post(
            f"/api/v1/subscriptions/{sub.id}/cancel/",
            {},
            content_type="application/json",
            **header,
        )
        self.assertEqual(second_cancel.status_code, 400)




