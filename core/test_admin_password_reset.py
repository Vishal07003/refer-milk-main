from django.test import TestCase, Client
from django.core import mail
from django.core.cache import cache
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

from accounts.models import User, AdminAuditLog


class AdminPasswordResetTests(TestCase):
    """
    Comprehensive test suite for the Forgot Password and Reset Password features
    of the Refer Milk / DudhDairy custom admin dashboard.
    """

    def setUp(self):
        self.client = Client()
        cache.clear()

        # 1. Eligible Active Staff Admin
        self.admin_user = User.objects.create_user(
            username="admin_reset_test",
            email="admin_reset@refermilk.com",
            mobile_number="9998800001",
            password="InitialAdminPass123!",
            role="admin",
            is_staff=True,
            is_active=True,
        )

        # 2. Ordinary Customer User
        self.customer_user = User.objects.create_user(
            username="cust_reset_test",
            email="customer_reset@refermilk.com",
            mobile_number="9998800002",
            password="InitialCustPass123!",
            role="customer",
            is_staff=False,
            is_superuser=False,
            is_active=True,
        )

        # 3. Delivery Partner User
        self.delivery_user = User.objects.create_user(
            username="delivery_reset_test",
            email="delivery_reset@refermilk.com",
            mobile_number="9998800003",
            password="InitialDelivPass123!",
            role="delivery_boy",
            is_staff=False,
            is_superuser=False,
            is_active=True,
        )

        # 4. Deactivated / Inactive Admin User
        self.inactive_admin = User.objects.create_user(
            username="inactive_admin_reset",
            email="inactive_admin@refermilk.com",
            mobile_number="9998800004",
            password="InactiveAdminPass123!",
            role="admin",
            is_staff=True,
            is_active=False,
        )

        # 5. Soft-deleted Admin User
        self.deleted_admin = User.objects.create_user(
            username="deleted_admin_reset",
            email="deleted_admin@refermilk.com",
            mobile_number="9998800005",
            password="DeletedAdminPass123!",
            role="admin",
            is_staff=True,
            is_active=True,
        )
        self.deleted_admin.is_deleted = True
        self.deleted_admin.save(update_fields=["is_deleted"])

    # =========================================================================
    # 1. Forgot Password Page & Form Rendering
    # =========================================================================

    def test_forgot_password_page_renders_cleanly(self):
        """GET /dairypanel/forgot-password/ returns 200 with branded template."""
        response = self.client.get("/dairypanel/forgot-password/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin Password Recovery")
        self.assertContains(response, "Mobile Number + OTP")
        self.assertContains(response, "Email Reset Link")
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_login_page_contains_forgot_password_link(self):
        """Custom admin login page includes link to forgot password."""
        response = self.client.get("/dairypanel/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/dairypanel/forgot-password/")
        self.assertContains(response, "Forgot Password?")

    def test_authenticated_admin_visiting_forgot_password_redirects(self):
        """Already authenticated admin is redirected to dashboard."""
        self.client.force_login(self.admin_user)
        response = self.client.get("/dairypanel/forgot-password/")
        self.assertRedirects(response, "/dairypanel/", fetch_redirect_response=False)

    # =========================================================================
    # 2. Email Dispatch & Account Enumeration Prevention
    # =========================================================================

    def test_forgot_password_valid_admin_sends_email(self):
        """Submitting registered admin email dispatches email and shows generic confirmation."""
        mail.outbox = []
        response = self.client.post("/dairypanel/forgot-password/", {
            "email": "admin_reset@refermilk.com",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an eligible administrator account is registered")

        # Verify an email was sent via Django test outbox
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, ["admin_reset@refermilk.com"])
        self.assertIn("Refer Milk DudhDairy — Admin Password Reset Request", sent_email.subject)
        self.assertIn("/dairypanel/reset-password/", sent_email.body)

    def test_forgot_password_nonexistent_email_shows_same_generic_message(self):
        """Submitting unregistered email displays exact same generic message (no enumeration) and sends no email."""
        mail.outbox = []
        response = self.client.post("/dairypanel/forgot-password/", {
            "email": "completely_unknown_999@example.com",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an eligible administrator account is registered")
        self.assertEqual(len(mail.outbox), 0)

    def test_forgot_password_customer_email_sends_no_email(self):
        """Customer email displays generic message but does NOT send reset email."""
        mail.outbox = []
        response = self.client.post("/dairypanel/forgot-password/", {
            "email": "customer_reset@refermilk.com",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an eligible administrator account is registered")
        self.assertEqual(len(mail.outbox), 0)

    def test_forgot_password_delivery_boy_email_sends_no_email(self):
        """Delivery partner email displays generic message but does NOT send reset email."""
        mail.outbox = []
        response = self.client.post("/dairypanel/forgot-password/", {
            "email": "delivery_reset@refermilk.com",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an eligible administrator account is registered")
        self.assertEqual(len(mail.outbox), 0)

    def test_forgot_password_inactive_admin_sends_no_email(self):
        """Inactive admin email displays generic message but does NOT send reset email."""
        mail.outbox = []
        response = self.client.post("/dairypanel/forgot-password/", {
            "email": "inactive_admin@refermilk.com",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an eligible administrator account is registered")
        self.assertEqual(len(mail.outbox), 0)

    def test_forgot_password_soft_deleted_admin_sends_no_email(self):
        """Soft-deleted admin email displays generic message but does NOT send reset email."""
        mail.outbox = []
        response = self.client.post("/dairypanel/forgot-password/", {
            "email": "deleted_admin@refermilk.com",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an eligible administrator account is registered")
        self.assertEqual(len(mail.outbox), 0)

    def test_forgot_password_rate_limiting(self):
        """Exceeding 5 requests triggers HTTP 429 rate-limit error."""
        for _ in range(5):
            res = self.client.post("/dairypanel/forgot-password/", {"email": "admin_reset@refermilk.com"})
            self.assertEqual(res.status_code, 200)

        # 6th attempt from same client
        res = self.client.post("/dairypanel/forgot-password/", {"email": "admin_reset@refermilk.com"})
        self.assertEqual(res.status_code, 429)
        self.assertContains(res, "Too many password recovery attempts", status_code=429)

    # =========================================================================
    # 3. Reset Password Confirmation & Token Validation
    # =========================================================================

    def test_reset_password_page_valid_token(self):
        """GET with valid uidb64 and token displays the reset form with 200 OK."""
        uidb64 = urlsafe_base64_encode(force_bytes(self.admin_user.pk))
        token = default_token_generator.make_token(self.admin_user)

        response = self.client.get(f"/dairypanel/reset-password/{uidb64}/{token}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Set New Password")
        self.assertContains(response, "new_password")
        self.assertContains(response, "confirm_password")

    def test_reset_password_page_invalid_token_rejected(self):
        """GET with invalid token returns 400 with Invalid or Expired Link notice."""
        uidb64 = urlsafe_base64_encode(force_bytes(self.admin_user.pk))
        bad_token = "invalid-token-12345"

        response = self.client.get(f"/dairypanel/reset-password/{uidb64}/{bad_token}/")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Invalid or Expired Link", status_code=400)

    def test_reset_password_page_invalid_uid_rejected(self):
        """GET with invalid base64 UID returns 400 with Invalid or Expired Link."""
        response = self.client.get("/dairypanel/reset-password/not-valid-base64/token-xyz/")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Invalid or Expired Link", status_code=400)

    def test_reset_password_customer_token_rejected(self):
        """Customer account reset link is rejected even if token format is valid."""
        uidb64 = urlsafe_base64_encode(force_bytes(self.customer_user.pk))
        token = default_token_generator.make_token(self.customer_user)

        response = self.client.get(f"/dairypanel/reset-password/{uidb64}/{token}/")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Invalid or Expired Link", status_code=400)

    def test_reset_password_password_mismatch_error(self):
        """POST with mismatched passwords displays clear validation error."""
        uidb64 = urlsafe_base64_encode(force_bytes(self.admin_user.pk))
        token = default_token_generator.make_token(self.admin_user)

        response = self.client.post(f"/dairypanel/reset-password/{uidb64}/{token}/", {
            "new_password": "NewSecurePassword123!",
            "confirm_password": "DifferentPassword123!",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Passwords do not match", status_code=400)

    def test_reset_password_validator_rejection(self):
        """POST with weak password rejected by Django validators (e.g. too short)."""
        uidb64 = urlsafe_base64_encode(force_bytes(self.admin_user.pk))
        token = default_token_generator.make_token(self.admin_user)

        response = self.client.post(f"/dairypanel/reset-password/{uidb64}/{token}/", {
            "new_password": "123",
            "confirm_password": "123",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "too short", status_code=400)

    # =========================================================================
    # 4. Successful Password Reset & Token Invalidation
    # =========================================================================

    def test_successful_password_reset_and_subsequent_login(self):
        """
        Valid submission successfully sets new password, renders success message,
        invalidates token against reuse, and enables login with the new password.
        """
        uidb64 = urlsafe_base64_encode(force_bytes(self.admin_user.pk))
        token = default_token_generator.make_token(self.admin_user)

        new_pass = "BrandNewAdminSecretPass2026!"
        response = self.client.post(f"/dairypanel/reset-password/{uidb64}/{token}/", {
            "new_password": new_pass,
            "confirm_password": new_pass,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Password Reset Complete")
        self.assertContains(response, "Proceed to Admin Login")

        # 1. Verify old password no longer works
        old_login_resp = self.client.post("/dairypanel/login/", {
            "username": "admin_reset_test",
            "password": "InitialAdminPass123!",
        })
        self.assertEqual(old_login_resp.status_code, 401)

        # 2. Verify new password successfully authenticates
        new_login_resp = self.client.post("/dairypanel/login/", {
            "username": "admin_reset_test",
            "password": new_pass,
        })
        self.assertRedirects(new_login_resp, "/dairypanel/", fetch_redirect_response=False)
        self.assertTrue("_auth_user_id" in self.client.session)

        # 3. Verify the token CANNOT be reused (token invalidation check)
        reuse_resp = self.client.get(f"/dairypanel/reset-password/{uidb64}/{token}/")
        self.assertEqual(reuse_resp.status_code, 400)
        self.assertContains(reuse_resp, "Invalid or Expired Link", status_code=400)

        # 4. Verify audit log entry was written
        audit_entry = AdminAuditLog.objects.filter(
            module="auth", action="password_reset_success", user=self.admin_user
        )
        self.assertTrue(audit_entry.exists())

    # =========================================================================
    # 5. Mobile Number + SMS OTP Recovery Tests
    # =========================================================================

    def test_mobile_otp_request_valid_admin_succeeds(self):
        """Eligible administrator can request OTP via SMS and gets directed to verification page."""
        from unittest.mock import patch

        with patch("accounts.sms_service.send_sms_otp_via_2factor", return_value=(True, "OTP sent successfully via SMS.", "sess_123")):
            response = self.client.post("/dairypanel/forgot-password/", {
                "recovery_mode": "mobile",
                "mobile_number": "9998800001",
            })
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Verify Security Code")
            self.assertContains(response, "session_id")
            self.assertContains(response, "••••••0001")

            # Check that an AdminPasswordResetSession was created
            from accounts.models import AdminPasswordResetSession
            session_obj = AdminPasswordResetSession.objects.filter(user=self.admin_user).first()
            self.assertIsNotNone(session_obj)
            self.assertFalse(session_obj.is_verified)
            self.assertFalse(session_obj.is_consumed)

    def test_mobile_otp_request_nonexistent_mobile_generic_response(self):
        """Unregistered mobile number returns generic message without revealing account absence."""
        response = self.client.post("/dairypanel/forgot-password/", {
            "recovery_mode": "mobile",
            "mobile_number": "9990009999",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an eligible administrator account is registered with this mobile number")

        from accounts.models import AdminPasswordResetSession
        self.assertFalse(AdminPasswordResetSession.objects.filter(mobile_number="9990009999").exists())

    def test_mobile_otp_request_customer_rejected_generically(self):
        """Customer mobile number returns generic message and does NOT generate OTP session."""
        response = self.client.post("/dairypanel/forgot-password/", {
            "recovery_mode": "mobile",
            "mobile_number": "9998800002",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an eligible administrator account is registered with this mobile number")

        from accounts.models import AdminPasswordResetSession
        self.assertFalse(AdminPasswordResetSession.objects.filter(user=self.customer_user).exists())

    def test_mobile_otp_request_delivery_boy_rejected_generically(self):
        """Delivery boy mobile returns generic message and does NOT generate OTP session."""
        response = self.client.post("/dairypanel/forgot-password/", {
            "recovery_mode": "mobile",
            "mobile_number": "9998800003",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an eligible administrator account is registered with this mobile number")

        from accounts.models import AdminPasswordResetSession
        self.assertFalse(AdminPasswordResetSession.objects.filter(user=self.delivery_user).exists())

    def test_mobile_otp_request_inactive_admin_rejected_generically(self):
        """Inactive admin mobile returns generic message and does NOT generate OTP session."""
        response = self.client.post("/dairypanel/forgot-password/", {
            "recovery_mode": "mobile",
            "mobile_number": "9998800004",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an eligible administrator account is registered with this mobile number")

        from accounts.models import AdminPasswordResetSession
        self.assertFalse(AdminPasswordResetSession.objects.filter(user=self.inactive_admin).exists())

    def test_mobile_otp_request_soft_deleted_admin_rejected_generically(self):
        """Soft-deleted admin mobile returns generic message and does NOT generate OTP session."""
        response = self.client.post("/dairypanel/forgot-password/", {
            "recovery_mode": "mobile",
            "mobile_number": "9998800005",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an eligible administrator account is registered with this mobile number")

        from accounts.models import AdminPasswordResetSession
        self.assertFalse(AdminPasswordResetSession.objects.filter(user=self.deleted_admin).exists())

    def test_mobile_otp_resend_cooldown(self):
        """Requesting OTP again within 60 seconds triggers cooldown rate limit."""
        from unittest.mock import patch
        with patch("accounts.sms_service.send_sms_otp_via_2factor", return_value=(True, "OK", "sess_1")):
            res1 = self.client.post("/dairypanel/forgot-password/", {
                "recovery_mode": "mobile",
                "mobile_number": "9998800001",
            })
            self.assertEqual(res1.status_code, 200)

            # Immediate re-request
            res2 = self.client.post("/dairypanel/forgot-password/", {
                "recovery_mode": "mobile",
                "mobile_number": "9998800001",
            })
            self.assertEqual(res2.status_code, 429)
            self.assertContains(res2, "wait 60 seconds", status_code=429)

    def test_mobile_otp_sms_failure_handled_safely(self):
        """When SMS gateway fails, return safe 503 error without claiming success."""
        from unittest.mock import patch
        with patch("accounts.sms_service.send_sms_otp_via_2factor", return_value=(False, "Gateway down", None)):
            response = self.client.post("/dairypanel/forgot-password/", {
                "recovery_mode": "mobile",
                "mobile_number": "9998800001",
            })
            self.assertEqual(response.status_code, 503)
            self.assertContains(response, "Unable to deliver SMS security code", status_code=503)

    def test_mobile_otp_verify_invalid_code_decrements_attempts(self):
        """Entering incorrect OTP increments attempt count and rejects with remaining attempts notice."""
        from datetime import timedelta
        from django.utils import timezone
        from accounts.models import AdminPasswordResetSession

        session_obj = AdminPasswordResetSession.objects.create(
            user=self.admin_user,
            mobile_number="9998800001",
            otp_hash=AdminPasswordResetSession.hash_otp("654321"),
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        response = self.client.post("/dairypanel/verify-otp/", {
            "session_id": session_obj.id,
            "otp": "000000",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Incorrect verification code. 4 attempt(s) remaining.", status_code=400)

        session_obj.refresh_from_db()
        self.assertEqual(session_obj.attempts_count, 1)

    def test_mobile_otp_verify_lockout_after_5_failed_attempts(self):
        """Exceeding 5 attempts locks out the session with HTTP 429."""
        from datetime import timedelta
        from django.utils import timezone
        from accounts.models import AdminPasswordResetSession

        session_obj = AdminPasswordResetSession.objects.create(
            user=self.admin_user,
            mobile_number="9998800001",
            otp_hash=AdminPasswordResetSession.hash_otp("654321"),
            attempts_count=5,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        response = self.client.post("/dairypanel/verify-otp/", {
            "session_id": session_obj.id,
            "otp": "654321",  # Even with correct code, locked out
        })
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Maximum verification attempts exceeded", status_code=429)

    def test_mobile_otp_expired_code_rejected(self):
        """OTP older than 5 minutes is rejected as expired."""
        from datetime import timedelta
        from django.utils import timezone
        from accounts.models import AdminPasswordResetSession

        session_obj = AdminPasswordResetSession.objects.create(
            user=self.admin_user,
            mobile_number="9998800001",
            otp_hash=AdminPasswordResetSession.hash_otp("654321"),
            expires_at=timezone.now() - timedelta(seconds=10),  # expired
        )

        response = self.client.post("/dairypanel/verify-otp/", {
            "session_id": session_obj.id,
            "otp": "654321",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "expired", status_code=400)

    def test_successful_otp_verification_and_password_reset(self):
        """
        Complete Mobile OTP flow:
        1. Request OTP & create session
        2. Verify OTP -> generates reset_token
        3. Submit new password -> updates password hash
        4. Reusing token fails
        5. Old password rejected; new password authenticates cleanly
        """
        from datetime import timedelta
        from django.utils import timezone
        from accounts.models import AdminPasswordResetSession

        session_obj = AdminPasswordResetSession.objects.create(
            user=self.admin_user,
            mobile_number="9998800001",
            otp_hash=AdminPasswordResetSession.hash_otp("847291"),
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        # 1. Verify OTP
        verify_resp = self.client.post("/dairypanel/verify-otp/", {
            "session_id": session_obj.id,
            "otp": "847291",
        })
        session_obj.refresh_from_db()
        self.assertTrue(session_obj.is_verified)
        self.assertTrue(bool(session_obj.reset_token))
        self.assertRedirects(verify_resp, f"/dairypanel/reset-password-otp/{session_obj.reset_token}/", fetch_redirect_response=False)

        # 2. Open reset page with token
        get_reset_resp = self.client.get(f"/dairypanel/reset-password-otp/{session_obj.reset_token}/")
        self.assertEqual(get_reset_resp.status_code, 200)
        self.assertContains(get_reset_resp, "Set New Password")

        # 3. Post new password
        new_secret = "BrandNewSecretViaOTP2026!"
        post_reset_resp = self.client.post(f"/dairypanel/reset-password-otp/{session_obj.reset_token}/", {
            "new_password": new_secret,
            "confirm_password": new_secret,
        })
        self.assertEqual(post_reset_resp.status_code, 200)
        self.assertContains(post_reset_resp, "Password Reset Complete")

        # 4. Token cannot be reused
        session_obj.refresh_from_db()
        self.assertTrue(session_obj.is_consumed)
        reused_resp = self.client.get(f"/dairypanel/reset-password-otp/{session_obj.reset_token}/")
        self.assertEqual(reused_resp.status_code, 400)
        self.assertContains(reused_resp, "Invalid or Expired Link", status_code=400)

        # 5. Old password no longer works
        old_login = self.client.post("/dairypanel/login/", {
            "username": "admin_reset_test",
            "password": "InitialAdminPass123!",
        })
        self.assertEqual(old_login.status_code, 401)

        # 6. New password authenticates successfully
        new_login = self.client.post("/dairypanel/login/", {
            "username": "admin_reset_test",
            "password": new_secret,
        })
        self.assertRedirects(new_login, "/dairypanel/", fetch_redirect_response=False)
        self.assertTrue("_auth_user_id" in self.client.session)
