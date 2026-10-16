from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User, AdminAuditLog


class AdminAuthenticationTests(TestCase):
    """
    Comprehensive test suite verifying production-safe authentication for the
    custom DudhDairy / Refer Milk Admin Dashboard and all /api/admin/ endpoints.
    """

    def setUp(self):
        self.client = Client()

        # 1. Staff Admin User
        self.admin_user = User.objects.create_user(
            username="admin_test",
            mobile_number="9999900001",
            password="AdminSecretPassword123!",
            role="admin",
            is_staff=True,
            is_active=True,
        )

        # 2. Ordinary Customer User
        self.customer_user = User.objects.create_user(
            username="customer_test",
            mobile_number="9999900002",
            password="CustomerPassword123!",
            role="customer",
            is_staff=False,
            is_superuser=False,
            is_active=True,
        )

        # 3. Delivery Partner User
        self.delivery_boy = User.objects.create_user(
            username="delivery_test",
            mobile_number="9999900003",
            password="DeliveryPassword123!",
            role="delivery_boy",
            is_staff=False,
            is_superuser=False,
            is_active=True,
        )

        # 4. Deactivated / Inactive Admin User
        self.inactive_admin = User.objects.create_user(
            username="inactive_admin_test",
            mobile_number="9999900004",
            password="InactivePassword123!",
            role="admin",
            is_staff=True,
            is_active=False,
        )

    # =========================================================================
    # 1. Admin Login Page and Form Rendering
    # =========================================================================

    def test_login_page_renders_cleanly(self):
        """GET /dairypanel/login/ returns 200 with branded template."""
        response = self.client.get("/dairypanel/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Refer Milk")
        self.assertContains(response, "Administrator Login")
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_admin_already_authenticated_redirects_to_dashboard(self):
        """Authenticated admin visiting /dairypanel/login/ is redirected to /dairypanel/."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/dairypanel/login/")
        self.assertRedirects(response, "/dairypanel/", fetch_redirect_response=False)

    # =========================================================================
    # 2. Authentication Flow & Role Validation
    # =========================================================================

    def test_admin_successful_login_with_username(self):
        """Valid admin username and password logs in and redirects to /dairypanel/."""
        response = self.client.post("/dairypanel/login/", {
            "username": "admin_test",
            "password": "AdminSecretPassword123!",
        })
        self.assertRedirects(response, "/dairypanel/", fetch_redirect_response=False)
        self.assertTrue("_auth_user_id" in self.client.session)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.admin_user.id)

    def test_admin_successful_login_with_mobile_number(self):
        """Valid admin phone number and password logs in and redirects to /dairypanel/."""
        response = self.client.post("/dairypanel/login/", {
            "username": "9999900001",
            "password": "AdminSecretPassword123!",
        })
        self.assertRedirects(response, "/dairypanel/", fetch_redirect_response=False)
        self.assertTrue("_auth_user_id" in self.client.session)

    def test_admin_login_preserves_safe_next_url(self):
        """Valid next url parameter is preserved upon login."""
        response = self.client.post("/dairypanel/login/", {
            "username": "admin_test",
            "password": "AdminSecretPassword123!",
            "next": "/dairypanel/?tab=customers",
        })
        self.assertRedirects(response, "/dairypanel/?tab=customers", fetch_redirect_response=False)

    def test_admin_login_blocks_malicious_open_redirect(self):
        """Malicious external URLs are stripped and fall back to /dairypanel/."""
        response = self.client.post("/dairypanel/login/", {
            "username": "admin_test",
            "password": "AdminSecretPassword123!",
            "next": "https://evil-attacker-site.com/steal-creds",
        })
        self.assertRedirects(response, "/dairypanel/", fetch_redirect_response=False)

    def test_login_invalid_password_rejected(self):
        """Wrong password returns 401 with clear invalid-credentials error message."""
        response = self.client.post("/dairypanel/login/", {
            "username": "admin_test",
            "password": "WrongPassword123!",
        })
        self.assertEqual(response.status_code, 401)
        self.assertContains(response, "Invalid username or password", status_code=401)
        self.assertFalse("_auth_user_id" in self.client.session)

    def test_login_inactive_admin_rejected(self):
        """Deactivated admin account returns 403 with inactive-account error message."""
        response = self.client.post("/dairypanel/login/", {
            "username": "inactive_admin_test",
            "password": "InactivePassword123!",
        })
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "inactive or disabled", status_code=403)
        self.assertFalse("_auth_user_id" in self.client.session)

    def test_customer_user_forbidden_from_admin_login(self):
        """Ordinary customer credentials are strictly rejected from admin login with 403."""
        response = self.client.post("/dairypanel/login/", {
            "username": "customer_test",
            "password": "CustomerPassword123!",
        })
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Ordinary customer or delivery partner accounts cannot access", status_code=403)
        self.assertFalse("_auth_user_id" in self.client.session)

    def test_delivery_partner_forbidden_from_admin_login(self):
        """Delivery partner credentials are strictly rejected from admin login with 403."""
        response = self.client.post("/dairypanel/login/", {
            "username": "delivery_test",
            "password": "DeliveryPassword123!",
        })
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Ordinary customer or delivery partner accounts cannot access", status_code=403)
        self.assertFalse("_auth_user_id" in self.client.session)

    # =========================================================================
    # 3. Protect Admin Dashboard View (/dairypanel/)
    # =========================================================================

    def test_unauthenticated_dashboard_access_redirects_to_login(self):
        """Unauthenticated GET /dairypanel/ redirects to /dairypanel/login/?next=/dairypanel/."""
        response = self.client.get("/dairypanel/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/dairypanel/login/?next="))

    def test_customer_access_to_dashboard_redirects_with_unauthorized_error(self):
        """Customer accessing /dairypanel/ directly is redirected to login with error parameter."""
        self.client.force_login(self.customer_user)
        response = self.client.get("/dairypanel/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("error=unauthorized", response.url)

    def test_delivery_partner_access_to_dashboard_redirects_with_unauthorized_error(self):
        """Delivery partner accessing /dairypanel/ directly is redirected to login."""
        self.client.force_login(self.delivery_boy)
        response = self.client.get("/dairypanel/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("error=unauthorized", response.url)

    def test_authenticated_admin_dashboard_access_granted(self):
        """Authenticated admin successfully loads dashboard (HTTP 200)."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/dairypanel/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operations & Cash Management Hub")
        self.assertIn("Cache-Control", response.headers)
        self.assertIn("no-cache", response.headers["Cache-Control"].lower())

    # =========================================================================
    # 4. Protect All Admin APIs (/api/admin/*)
    # =========================================================================

    def test_unauthenticated_api_request_returns_json_401(self):
        """Unauthenticated API request returns JSON 401, NOT an HTML page redirect."""
        response = self.client.get("/api/admin/stats/")
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data.get("authenticated"))
        self.assertIn("Authentication required", data.get("error", ""))

    def test_customer_api_request_returns_json_403(self):
        """Customer user attempting to call admin API returns JSON 403."""
        self.client.force_login(self.customer_user)
        response = self.client.get("/api/admin/stats/")
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data.get("authorized"))
        self.assertIn("Permission denied", data.get("error", ""))

    def test_authenticated_admin_api_request_succeeds(self):
        """Authenticated admin calling admin API returns HTTP 200 JSON."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/api/admin/stats/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("cash_collections", data)

    # =========================================================================
    # 5. Logout Flow & Session Destruction
    # =========================================================================

    def test_logout_clears_session_and_redirects(self):
        """POST /dairypanel/logout/ terminates session and redirects to /dairypanel/login/."""
        self.client.force_login(self.admin_user)
        self.assertTrue("_auth_user_id" in self.client.session)

        response = self.client.post("/dairypanel/logout/")
        self.assertRedirects(response, "/dairypanel/login/", fetch_redirect_response=False)
        self.assertFalse("_auth_user_id" in self.client.session)

        # Accessing /dairypanel/ after logout must redirect back to login
        subsequent = self.client.get("/dairypanel/")
        self.assertEqual(subsequent.status_code, 302)
        self.assertTrue(subsequent.url.startswith("/dairypanel/login/?next="))

    def test_audit_logs_record_login_and_logout(self):
        """Admin login and logout events are recorded in AdminAuditLog."""
        self.client.post("/dairypanel/login/", {
            "username": "admin_test",
            "password": "AdminSecretPassword123!",
        })
        self.client.post("/dairypanel/logout/")

        login_logs = AdminAuditLog.objects.filter(module="auth", action="login_success", user=self.admin_user)
        self.assertTrue(login_logs.exists())

        logout_logs = AdminAuditLog.objects.filter(module="auth", action="logout", user=self.admin_user)
        self.assertTrue(logout_logs.exists())
