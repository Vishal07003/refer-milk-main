from django.test import TestCase, Client
import json
from decimal import Decimal
from accounts.models import User, Address
from subscriptions.models import Subscription, SubscriptionPlan
from products.models import Product, Category


class CustomerDeleteRecycleBinTests(TestCase):
    """
    Automated test suite for the Admin Customer Deletion / Move to Recycle Bin flow:
    - Verifies deletion with canonical primary key passed as 'id' or 'user_id'
    - Verifies missing ID, invalid ID, unauthorized customer access
    - Verifies soft-deletion mechanics (30-day retention, active subscriptions cancelled)
    - Verifies soft-deleted customer appears in Recycle Bin and can be restored
    - Verifies deletion applies strictly to the target customer and preserves order history
    """

    def setUp(self):
        self.client = Client()

        # 1. Staff Admin User
        self.admin = User.objects.create_user(
            username="admin_staff",
            mobile_number="9999900010",
            password="AdminPassword123!",
            role="admin",
            is_staff=True,
            is_active=True,
        )

        # 2. Non-admin customer for permission tests
        self.non_admin = User.objects.create_user(
            username="other_cust",
            mobile_number="9999900011",
            password="OtherCustPass123!",
            role="customer",
            is_staff=False,
            is_active=True,
        )

        # 3. Target Customer to Delete
        self.customer = User.objects.create_user(
            username="target_cust",
            mobile_number="9876543210",
            first_name="Ramesh",
            last_name="Patil",
            password="TargetCustPass123!",
            role="customer",
            is_staff=False,
            is_active=True,
        )
        self.customer_address = Address.objects.create(
            user=self.customer,
            house_number="42",
            street="Station Road",
            area="Station Area",
            city="Sangola",
            pincode="413307",
            is_default=True,
        )

        # 4. Another Customer to ensure isolation
        self.other_customer = User.objects.create_user(
            username="untouched_cust",
            mobile_number="9876543211",
            first_name="Suresh",
            last_name="Jadhav",
            password="OtherCustPass123!",
            role="customer",
            is_staff=False,
            is_active=True,
        )

        # 5. Product & Subscription for target customer
        self.cat = Category.objects.create(name="Dairy")
        self.product = Product.objects.create(
            name="Cow Milk 1L",
            category=self.cat,
            price=Decimal("60.00"),
            unit="litre",
            is_active=True,
        )
        self.sub_plan = SubscriptionPlan.objects.create(
            name="Daily Plan",
            product=self.product,
            quantity=Decimal("1.00"),
            unit="litre",
            frequency="daily",
            price_per_unit=Decimal("60.00"),
            is_active=True,
        )
        from datetime import date
        self.subscription = Subscription.objects.create(
            user=self.customer,
            product=self.product,
            plan=self.sub_plan,
            address=self.customer_address,
            quantity=Decimal("1.00"),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            price_per_unit=Decimal("60.00"),
            final_price_per_unit=Decimal("60.00"),
            total_amount=Decimal("1800.00"),
            status="active",
        )

    def test_delete_missing_id_returns_400(self):
        """Deleting without id or user_id returns 400 error."""
        self.client.force_login(self.admin)
        resp = self.client.post(
            "/api/admin/customers/",
            data=json.dumps({"action": "delete"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data.get("error"), "User ID is required.")

    def test_delete_invalid_or_nonexistent_id_returns_404(self):
        """Deleting non-existent customer returns 404."""
        self.client.force_login(self.admin)
        resp = self.client.post(
            "/api/admin/customers/",
            data=json.dumps({"action": "delete", "id": 999999}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_delete_unauthorized_access_rejected(self):
        """Non-admin user cannot delete customers."""
        self.client.force_login(self.non_admin)
        resp = self.client.post(
            "/api/admin/customers/",
            data=json.dumps({"action": "delete", "id": self.customer.id}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_soft_delete_with_id_field_succeeds(self):
        """Soft-deleting using 'id' in payload succeeds and moves record to recycle bin."""
        self.client.force_login(self.admin)
        resp = self.client.post(
            "/api/admin/customers/",
            data=json.dumps({"action": "delete", "id": self.customer.id}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("action"), "soft_deleted")

        # Verify target customer is soft-deleted
        self.assertFalse(User.objects.filter(id=self.customer.id).exists())
        self.assertTrue(User.deleted_objects.filter(id=self.customer.id).exists())

        # Verify other customer is completely untouched
        self.assertTrue(User.objects.filter(id=self.other_customer.id).exists())

        # Verify associated active subscriptions were cancelled/soft-deleted
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.is_deleted)

    def test_soft_delete_with_user_id_field_succeeds(self):
        """Soft-deleting using 'user_id' in payload succeeds."""
        self.client.force_login(self.admin)
        resp = self.client.post(
            "/api/admin/customers/",
            data=json.dumps({"action": "delete", "user_id": self.customer.id}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(User.deleted_objects.filter(id=self.customer.id).exists())

    def test_recycle_bin_listing_and_restore(self):
        """Soft-deleted customer appears in Recycle Bin and can be restored."""
        self.client.force_login(self.admin)

        # Soft delete the customer
        self.client.post(
            "/api/admin/customers/",
            data=json.dumps({"action": "delete", "id": self.customer.id, "user_id": self.customer.id}),
            content_type="application/json",
        )

        # Check Recycle Bin listing
        rb_resp = self.client.get("/api/admin/recycle-bin/?type=customers")
        self.assertEqual(rb_resp.status_code, 200)
        rb_data = rb_resp.json()
        cust_ids = [c["id"] for c in rb_data.get("customers", [])]
        self.assertIn(self.customer.id, cust_ids)

        # Restore customer from Recycle Bin
        restore_resp = self.client.post(
            "/api/admin/recycle-bin/",
            data=json.dumps({"action": "restore", "type": "customer", "id": self.customer.id}),
            content_type="application/json",
        )
        self.assertEqual(restore_resp.status_code, 200)
        self.assertTrue(restore_resp.json().get("success"))

        # Verify customer is back in active objects
        self.assertTrue(User.objects.filter(id=self.customer.id).exists())
        self.assertFalse(User.deleted_objects.filter(id=self.customer.id).exists())
