from unittest.mock import patch, MagicMock
from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User, Referral, OTP


class ReferralSystemTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Customer A
        self.customer_a = User.objects.create_user(
            username="9876543210",
            mobile_number="9876543210",
            role="customer",
            first_name="Customer",
            last_name="A",
        )

        # Customer B
        self.customer_b = User.objects.create_user(
            username="9999999999",
            mobile_number="9999999999",
            role="customer",
            first_name="Customer",
            last_name="B",
        )

        # Delivery Boy
        self.delivery_boy = User.objects.create_user(
            username="8888888888",
            mobile_number="8888888888",
            role="delivery_boy",
            first_name="Delivery",
            last_name="Boy",
        )

    # 1. New customer gets referral code with DD prefix
    def test_01_new_customer_gets_dd_referral_code(self):
        self.assertTrue(self.customer_a.referral_code.startswith("DD"))
        self.assertEqual(len(self.customer_a.referral_code), 10)

    # 2. Referral code is unique
    def test_02_referral_code_is_unique(self):
        self.assertNotEqual(
            self.customer_a.referral_code, self.customer_b.referral_code
        )

    # 3. Existing customer keeps same referral code
    def test_03_existing_customer_keeps_same_code(self):
        code_before = self.customer_a.referral_code
        self.customer_a.first_name = "UpdatedName"
        self.customer_a.save()
        self.customer_a.refresh_from_db()
        self.assertEqual(self.customer_a.referral_code, code_before)

    # 4. Valid referral code works
    def test_04_valid_referral_code_works(self):
        self.client.force_authenticate(user=self.customer_b)
        url = reverse("accounts:apply-referral")
        response = self.client.post(
            url, {"referral_code": self.customer_a.referral_code}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("message"), "Referral applied successfully.")
        self.assertEqual(response.data.get("discount"), 50)

        # Check DB
        self.customer_b.refresh_from_db()
        self.assertEqual(self.customer_b.referred_by, self.customer_a)
        self.assertTrue(
            Referral.objects.filter(
                referrer=self.customer_a, referred_user=self.customer_b
            ).exists()
        )

    # 5. Invalid referral code fails
    def test_05_invalid_referral_code_fails(self):
        self.client.force_authenticate(user=self.customer_b)
        url = reverse("accounts:apply-referral")
        response = self.client.post(url, {"referral_code": "INVALID99"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # 6. Self-referral fails
    def test_06_self_referral_fails(self):
        self.client.force_authenticate(user=self.customer_a)
        url = reverse("accounts:apply-referral")
        response = self.client.post(
            url, {"referral_code": self.customer_a.referral_code}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # 7. Customer cannot apply referral twice
    def test_07_cannot_apply_referral_twice(self):
        self.client.force_authenticate(user=self.customer_b)
        url = reverse("accounts:apply-referral")
        self.client.post(url, {"referral_code": self.customer_a.referral_code})

        # Try second time
        response2 = self.client.post(
            url, {"referral_code": self.customer_a.referral_code}
        )
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)

    # 8. Referral is linked to correct referrer
    def test_08_referral_linked_to_correct_referrer(self):
        self.client.force_authenticate(user=self.customer_b)
        url = reverse("accounts:apply-referral")
        self.client.post(url, {"referral_code": self.customer_a.referral_code})

        ref = Referral.objects.get(referred_user=self.customer_b)
        self.assertEqual(ref.referrer, self.customer_a)
        self.assertEqual(ref.referral_code, self.customer_a.referral_code)

    # 9. Unauthenticated user cannot apply referral
    def test_09_unauthenticated_user_cannot_apply(self):
        url = reverse("accounts:apply-referral")
        response = self.client.post(
            url, {"referral_code": self.customer_a.referral_code}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # 10. Delivery Partner cannot use customer referral
    def test_10_delivery_partner_cannot_apply_referral(self):
        self.client.force_authenticate(user=self.delivery_boy)
        url = reverse("accounts:apply-referral")
        response = self.client.post(
            url, {"referral_code": self.customer_a.referral_code}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # 11. Profile API returns referral code
    def test_11_profile_api_returns_referral_code(self):
        self.client.force_authenticate(user=self.customer_a)
        url = reverse("accounts:profile")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile_data = response.data.get("profile", response.data)
        self.assertEqual(
            profile_data.get("referral_code"), self.customer_a.referral_code
        )

    # 12. My-referrals API returns correct statistics
    def test_12_my_referrals_api_returns_statistics(self):
        # Customer B applies Customer A's code
        self.client.force_authenticate(user=self.customer_b)
        url_apply = reverse("accounts:apply-referral")
        self.client.post(url_apply, {"referral_code": self.customer_a.referral_code})

        # Fetch My Referrals for Customer A
        self.client.force_authenticate(user=self.customer_a)
        url_my_ref = reverse("accounts:my-referrals")
        response = self.client.get(url_my_ref)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data.get("referral_code"), self.customer_a.referral_code
        )
        self.assertEqual(response.data.get("total_referrals"), 1)
        self.assertEqual(response.data.get("successful_referrals"), 1)
        self.assertEqual(response.data.get("total_rewards"), 50.0)
        self.assertEqual(len(response.data.get("referrals")), 1)


from accounts.models import Wallet, WalletTransaction
from decimal import Decimal


class WalletSystemTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.customer = User.objects.create_user(
            username="9111111111",
            mobile_number="9111111111",
            role="customer",
            first_name="Wallet",
            last_name="Customer",
        )

        self.delivery_boy = User.objects.create_user(
            username="9222222222",
            mobile_number="9222222222",
            role="delivery_boy",
            first_name="Delivery",
            last_name="Boy",
        )

    def test_customer_wallet_auto_created(self):
        self.assertTrue(hasattr(self.customer, "wallet"))
        self.assertEqual(self.customer.wallet.balance, Decimal("0.00"))

    def test_delivery_partner_wallet_access_forbidden(self):
        self.client.force_authenticate(user=self.delivery_boy)
        response = self.client.get("/api/v1/wallet/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_wallet_balance(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get("/api/v1/wallet/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("balance"), "0.00")

    def test_create_topup_validates_amount(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post("/api/v1/wallet/create-topup/", {"amount": -50})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_topup_order_success(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post("/api/v1/wallet/create-topup/", {"amount": 500})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("order_id", response.data)
        self.assertEqual(response.data.get("amount"), 50000)

    def test_verify_topup_credits_wallet(self):
        self.client.force_authenticate(user=self.customer)
        topup_res = self.client.post("/api/v1/wallet/create-topup/", {"amount": 500})
        order_id = topup_res.data.get("order_id")

        verify_res = self.client.post(
            "/api/v1/wallet/verify-topup/",
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": "pay_test123",
                "razorpay_signature": "sig_test123",
            },
        )
        self.assertEqual(verify_res.status_code, status.HTTP_200_OK)
        self.assertEqual(verify_res.data.get("balance"), "500.00")

        self.customer.wallet.refresh_from_db()
        self.assertEqual(self.customer.wallet.balance, Decimal("500.00"))

    def test_duplicate_verify_idempotent(self):
        self.client.force_authenticate(user=self.customer)
        topup_res = self.client.post("/api/v1/wallet/create-topup/", {"amount": 500})
        order_id = topup_res.data.get("order_id")

        self.client.post(
            "/api/v1/wallet/verify-topup/",
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": "pay_test123",
                "razorpay_signature": "sig_test123",
            },
        )

        verify_res2 = self.client.post(
            "/api/v1/wallet/verify-topup/",
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": "pay_test123",
                "razorpay_signature": "sig_test123",
            },
        )
        self.assertEqual(verify_res2.status_code, status.HTTP_200_OK)
        self.assertEqual(verify_res2.data.get("message"), "Payment already processed.")

        self.customer.wallet.refresh_from_db()
        self.assertEqual(self.customer.wallet.balance, Decimal("500.00"))

    def test_wallet_transactions_history(self):
        self.client.force_authenticate(user=self.customer)
        topup_res = self.client.post("/api/v1/wallet/create-topup/", {"amount": 500})
        order_id = topup_res.data.get("order_id")

        self.client.post(
            "/api/v1/wallet/verify-topup/",
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": "pay_test123",
                "razorpay_signature": "sig_test123",
            },
        )

        tx_res = self.client.get("/api/v1/wallet/transactions/")
        self.assertEqual(tx_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(tx_res.data.get("transactions")), 1)

    def test_unauthorized_request_rejected(self):
        response = self.client.get("/api/v1/wallet/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_payment_history_endpoint(self):
        from subscriptions.models import Payment

        Payment.objects.create(
            user=self.customer,
            amount=Decimal("250.00"),
            payment_method="wallet",
            payment_status="completed",
            notes="Subscription payment",
        )
        self.client.force_authenticate(user=self.customer)
        response = self.client.get("/api/v1/subscriptions/payments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("total"), 1)
        self.assertEqual(len(response.data.get("payments")), 1)
        self.assertEqual(response.data.get("total_paid"), "250.00")


class TwoFactorSMSOTPTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.send_otp_url = reverse("accounts:send-otp")
        self.verify_otp_url = reverse("accounts:verify-otp")

    @override_settings(TWOFACTOR_API_KEY="test_mock_api_key_12345", TWOFACTOR_OTP_TEMPLATE_NAME="")
    @patch("requests.get")
    def test_send_otp_success_with_mocked_2factor_provider(self, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Status": "Success",
            "Details": "test-session-uuid-1234-5678",
        }
        mock_requests_get.return_value = mock_response

        response = self.client.post(self.send_otp_url, {"mobile_number": "9876543210"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("msg"), "OTP sent successfully via SMS.")

        # Ensure requests.get was invoked with 2Factor API V1 format
        self.assertTrue(mock_requests_get.called)
        called_url = mock_requests_get.call_args[0][0]
        self.assertIn("https://2factor.in/API/V1/test_mock_api_key_12345/SMS/919876543210/", called_url)

        # Check that OTP record was created in the database
        otp_record = OTP.objects.filter(mobile_number="9876543210", is_used=False).first()
        self.assertIsNotNone(otp_record)
        self.assertEqual(len(otp_record.otp), 6)

    @override_settings(TWOFACTOR_API_KEY="test_mock_api_key_12345", TWOFACTOR_OTP_TEMPLATE_NAME="DairyLoginOTP")
    @patch("requests.get")
    def test_send_otp_with_custom_template_name(self, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Status": "Success",
            "Details": "test-session-uuid-custom-template",
        }
        mock_requests_get.return_value = mock_response

        response = self.client.post(self.send_otp_url, {"mobile_number": "9876543210"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        called_url = mock_requests_get.call_args[0][0]
        self.assertTrue(called_url.endswith("/DairyLoginOTP"))

    @override_settings(TWOFACTOR_API_KEY="test_mock_api_key_12345")
    @patch("requests.get")
    def test_send_otp_provider_rejection_returns_400(self, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Status": "Error",
            "Details": "Insufficient SMS balance",
        }
        mock_requests_get.return_value = mock_response

        response = self.client.post(self.send_otp_url, {"mobile_number": "9876543210"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Insufficient SMS balance", response.data.get("error"))

    @override_settings(TWOFACTOR_API_KEY="test_mock_api_key_12345")
    @patch("requests.get")
    def test_send_otp_gateway_timeout_handles_safely(self, mock_requests_get):
        import requests
        mock_requests_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        response = self.client.post(self.send_otp_url, {"mobile_number": "9876543210"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("timed out", response.data.get("error").lower())

    @override_settings(TWOFACTOR_API_KEY="test_mock_api_key_12345")
    @patch("requests.get")
    def test_send_and_verify_otp_end_to_end_jwt_login(self, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Status": "Success",
            "Details": "session-e2e-ok",
        }
        mock_requests_get.return_value = mock_response

        # 1. Send OTP
        send_res = self.client.post(self.send_otp_url, {"mobile_number": "9123456789"})
        self.assertEqual(send_res.status_code, status.HTTP_200_OK)

        otp_record = OTP.objects.get(mobile_number="9123456789", is_used=False)

        # 2. Verify OTP with correct code
        verify_res = self.client.post(
            self.verify_otp_url,
            {"mobile_number": "9123456789", "otp": otp_record.otp},
        )
        self.assertEqual(verify_res.status_code, status.HTTP_200_OK)
        self.assertIn("access", verify_res.data)
        self.assertIn("refresh", verify_res.data)
        self.assertEqual(verify_res.data["user"]["mobile_number"], "9123456789")

        # Verify OTP is marked used
        otp_record.refresh_from_db()
        self.assertTrue(otp_record.is_used)

        # 3. Trying to reuse same OTP fails
        reuse_res = self.client.post(
            self.verify_otp_url,
            {"mobile_number": "9123456789", "otp": otp_record.otp},
        )
        self.assertEqual(reuse_res.status_code, status.HTTP_400_BAD_REQUEST)


class AddressAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="9111111111",
            mobile_number="9111111111",
            role="customer",
            first_name="Address",
            last_name="Tester",
        )
        self.client.force_authenticate(user=self.user)
        self.address_url = reverse("accounts:address-list-create")

    def test_create_address_with_actual_city_and_pincode(self):
        payload = {
            "label": "home",
            "house_number": "Flat 101",
            "street": "MG Road",
            "area": "Camp",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411001",
            "country": "India",
        }
        res = self.client.post(self.address_url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["address"]["city"], "Pune")
        self.assertEqual(res.data["address"]["pincode"], "411001")
        self.assertNotEqual(res.data["address"]["city"], "Sangola")
        self.assertNotEqual(res.data["address"]["pincode"], "413307")

    def test_update_existing_address_preserves_and_updates_exact_fields(self):
        # Create initial address
        from accounts.models import Address
        addr = Address.objects.create(
            user=self.user,
            label="home",
            house_number="B-204",
            street="Station Link",
            area="Sector 4",
            city="Kolhapur",
            state="Maharashtra",
            pincode="416001",
        )
        detail_url = reverse("accounts:address-detail", kwargs={"pk": addr.id})

        # Update to another distinct city & pincode
        update_payload = {
            "city": "Solapur",
            "pincode": "413001",
        }
        res = self.client.put(detail_url, update_payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["address"]["city"], "Solapur")
        self.assertEqual(res.data["address"]["pincode"], "413001")

        addr.refresh_from_db()
        self.assertEqual(addr.city, "Solapur")
        self.assertEqual(addr.pincode, "413001")

    def test_create_address_requires_city_and_pincode(self):
        # When city or pincode is missing or blank, backend rejects with 400
        payload = {
            "label": "home",
            "house_number": "Flat 5",
            "street": "Main Road",
            "area": "Downtown",
            "city": "",
            "state": "Maharashtra",
            "pincode": "",
        }
        res = self.client.post(self.address_url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("city", res.data)
        self.assertIn("pincode", res.data)
