"""
Tests pour le paiement en mode sandbox : confirmation simulée, sécurité
d'accès (un client ne voit que ses propres paiements).
"""
import hashlib
import hmac
import json
import time
from unittest import mock

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient
from apps.users.models import User, Role, UserRole
from apps.catalog.models import Store
from apps.orders.models import Order
from apps.payments.models import Payment, Refund
from apps.payments.gateways import (
    OrangeMoneyGateway, PaymentGatewayError, WaveGateway, verify_wave_signature,
)


@override_settings(PAYMENT_SANDBOX=True)
class PaymentSandboxTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        Role.objects.get_or_create(name=Role.RoleName.MERCHANT)

        self.customer = self._make_user("client@example.com", Role.RoleName.CLIENT)
        self.other_customer = self._make_user("other@example.com", Role.RoleName.CLIENT)
        merchant = self._make_user("merchant@example.com", Role.RoleName.MERCHANT)
        store = Store.objects.create(owner=merchant, name="Boutique")

        self.order = Order.objects.create(customer=self.customer, store=store, total_amount=10000)
        self.payment = Payment.objects.create(order=self.order, amount=10000, method="wave")

    def _make_user(self, email, role_name):
        user = User.objects.create_user(username=email, email=email, password="testpass123", is_verified=True)
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def test_customer_only_sees_own_payments(self):
        self.client.force_authenticate(self.other_customer)
        response = self.client.get("/api/payments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_initiate_returns_sandbox_response_by_default(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post(f"/api/payments/{self.payment.id}/initiate/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["sandbox"])
        self.payment.refresh_from_db()
        self.assertTrue(self.payment.provider_ref.startswith("SANDBOX-"))

    def test_sandbox_confirm_success_marks_payment_and_order_paid(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post(f"/api/payments/{self.payment.id}/sandbox-confirm/", {"outcome": "success"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESS)
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_sandbox_confirm_failure_does_not_advance_order(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post(f"/api/payments/{self.payment.id}/sandbox-confirm/", {"outcome": "failed"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.FAILED)
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_other_customer_cannot_confirm_payment(self):
        # Le paiement n'appartient pas à son périmètre : absent de son queryset,
        # donc 404 (et non 403, qui révélerait son existence).
        self.client.force_authenticate(self.other_customer)
        response = self.client.post(f"/api/payments/{self.payment.id}/sandbox-confirm/", {"outcome": "success"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    @override_settings(PAYMENT_SANDBOX=False)
    def test_sandbox_confirm_disabled_outside_sandbox_mode(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post(f"/api/payments/{self.payment.id}/sandbox-confirm/", {"outcome": "success"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class RefundStatusFilterTests(TestCase):
    """Le filtre ?status= de la liste admin des remboursements (admin-refunds)."""

    def setUp(self):
        self.client = APIClient()
        Role.objects.get_or_create(name=Role.RoleName.ADMIN)
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        Role.objects.get_or_create(name=Role.RoleName.MERCHANT)

        admin = User.objects.create_user(username="admin@example.com", email="admin@example.com", password="p", is_verified=True)
        UserRole.objects.create(user=admin, role=Role.objects.get(name=Role.RoleName.ADMIN))
        self.admin = admin

        customer = User.objects.create_user(username="client@example.com", email="client@example.com", password="p", is_verified=True)
        UserRole.objects.create(user=customer, role=Role.objects.get(name=Role.RoleName.CLIENT))

        merchant = User.objects.create_user(username="merchant@example.com", email="merchant@example.com", password="p", is_verified=True)
        UserRole.objects.create(user=merchant, role=Role.objects.get(name=Role.RoleName.MERCHANT))

        store = Store.objects.create(owner=merchant, name="Boutique")
        order = Order.objects.create(customer=customer, store=store, total_amount=10000)
        payment = Payment.objects.create(order=order, amount=10000, method="wave")

        self.pending_refund = Refund.objects.create(payment=payment, amount=6000, reason="Annulation")
        self.completed_refund = Refund.objects.create(
            payment=payment, amount=4000, reason="Satisfait", status=Refund.Status.COMPLETED
        )

    def test_admin_filters_refunds_by_status(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/payments/refunds/?status=pending")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.pending_refund.id)

    def test_admin_sees_all_refunds_without_filter(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/payments/refunds/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)

    def test_customer_status_filter_only_scopes_own_refunds(self):
        customer = self.pending_refund.payment.order.customer
        self.client.force_authenticate(customer)
        response = self.client.get("/api/payments/refunds/?status=completed")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.completed_refund.id)


class FakeResponse:
    """Faux objet réponse HTTP pour mocker requests sans réseau."""

    def __init__(self, payload, status_code=200, text=None):
        self.payload = payload
        self.status_code = status_code
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        return self.payload


@override_settings(
    PAYMENT_SANDBOX=False,
    WAVE_API_KEY="wave_test_key",
    WAVE_API_BASE_URL="https://api.wave.test",
    FRONTEND_URL="http://localhost:3004",
    BACKEND_URL="http://localhost:8080/api",
    ORANGE_MONEY_CLIENT_ID="om_client",
    ORANGE_MONEY_CLIENT_SECRET="om_secret",
    ORANGE_MONEY_MERCHANT_KEY="om_merchant",
    ORANGE_MONEY_API_BASE_URL="https://api.orange.test",
    ORANGE_MONEY_COUNTRY_PATH="sn",
    ORANGE_MONEY_CURRENCY="XOF",
)
class GatewayIntegrationTests(TestCase):
    """Intégration réelle Wave/Orange Money (appels HTTP mockés)."""

    def setUp(self):
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        merchant = User.objects.create_user(username="m@x.com", email="m@x.com", password="p", is_verified=True)
        Role.objects.get_or_create(name=Role.RoleName.MERCHANT)
        UserRole.objects.create(user=merchant, role=Role.objects.get(name=Role.RoleName.MERCHANT))
        store = Store.objects.create(owner=merchant, name="Boutique")
        client = User.objects.create_user(username="c@x.com", email="c@x.com", password="p", is_verified=True)
        UserRole.objects.create(user=client, role=Role.objects.get(name=Role.RoleName.CLIENT))
        self.order = Order.objects.create(customer=client, store=store, total_amount=10000)
        self.payment = Payment.objects.create(order=self.order, amount=10000, method="wave")

    def test_wave_initiate_posts_checkout_session(self):
        posted = {}

        def fake_post(url, **kwargs):
            posted["url"] = url
            posted["headers"] = kwargs["headers"]
            posted["json"] = kwargs["json"]
            return FakeResponse({"id": "cos-test123", "wave_launch_url": "https://pay.wave.test/c/cos-test123"})

        with mock.patch("apps.payments.gateways.requests.post", side_effect=fake_post):
            result = WaveGateway().initiate(self.payment)

        self.assertEqual(posted["url"], "https://api.wave.test/v1/checkout/sessions")
        self.assertEqual(posted["headers"]["Authorization"], "Bearer wave_test_key")
        self.assertEqual(posted["json"]["amount"], "10000")
        self.assertEqual(posted["json"]["currency"], "XOF")
        self.assertEqual(posted["json"]["client_reference"], str(self.payment.id))
        self.assertIn("/order-confirmed?order=", posted["json"]["success_url"])
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.provider_ref, "cos-test123")
        self.assertEqual(result["sandbox"], False)
        self.assertEqual(result["checkout_url"], "https://pay.wave.test/c/cos-test123")

    def test_wave_initiate_requires_api_key(self):
        with override_settings(WAVE_API_KEY=""):
            with self.assertRaises(PaymentGatewayError):
                WaveGateway().initiate(self.payment)

    def test_wave_initiate_raises_on_provider_refusal(self):
        with mock.patch(
            "apps.payments.gateways.requests.post",
            return_value=FakeResponse({"message": "bad key"}, status_code=401),
        ):
            with self.assertRaises(PaymentGatewayError) as ctx:
                WaveGateway().initiate(self.payment)
        self.assertIn("401", str(ctx.exception))

    def test_orange_money_initiate_exchanges_oauth_for_payment(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            if "oauth" in url:
                return FakeResponse({"access_token": "token-abc"})
            return FakeResponse(
                {"pay_token": "pay-xyz", "payment_url": "https://om.test/pay/pay-xyz", "notif_token": "notif-123"}
            )

        with mock.patch("apps.payments.gateways.requests.post", side_effect=fake_post):
            result = OrangeMoneyGateway().initiate(self.payment)

        self.assertEqual(calls[0][0], "https://api.orange.test/oauth/v3/token")
        self.assertEqual(calls[0][1]["data"], {"grant_type": "client_credentials"})
        webpayment_url, webpayment_kwargs = calls[1]
        self.assertEqual(webpayment_url, "https://api.orange.test/orange-money-webpay/sn/v1/webpayment")
        self.assertEqual(webpayment_kwargs["headers"]["Authorization"], "Bearer token-abc")
        body = webpayment_kwargs["json"]
        self.assertEqual(body["amount"], 10000)
        self.assertEqual(body["currency"], "XOF")
        self.assertEqual(body["merchant_key"], "om_merchant")
        self.assertIn("/payments/webhook/orange_money/", body["notif_url"])
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.provider_ref, "pay-xyz")
        self.assertEqual(self.payment.metadata["orange_money"]["notif_token"], "notif-123")
        self.assertEqual(result["checkout_url"], "https://om.test/pay/pay-xyz")

    def test_orange_money_uses_dev_path_in_sandbox(self):
        with override_settings(PAYMENT_SANDBOX=True):
            gateway = OrangeMoneyGateway()
            self.assertIn("dev", gateway._webpayment_path())

    def test_orange_money_requires_merchant_key(self):
        with override_settings(ORANGE_MONEY_MERCHANT_KEY=""):
            with self.assertRaises(PaymentGatewayError):
                OrangeMoneyGateway().initiate(self.payment)

    def test_verify_wave_signature_rejects_tampered_body(self):
        secret, body = "whsec_test", '{"id":"evt_1","type":"checkout.session.completed"}'
        ts = str(int(time.time()))
        signature = hmac.new(secret.encode(), f"{ts}{body}".encode(), hashlib.sha256).hexdigest()
        header = f"t={ts},v1={signature}"
        self.assertTrue(verify_wave_signature(secret, header, body.encode()))
        self.assertFalse(verify_wave_signature(secret, header, b'{"id":"evt_2"}'))
        self.assertFalse(verify_wave_signature(secret, "t=1,v1=deadbeef", body.encode()))

    def test_verify_wave_signature_rejects_old_timestamp(self):
        secret, body = "whsec_test", "{}"
        ts = str(int(time.time()) - 600)
        signature = hmac.new(secret.encode(), f"{ts}{body}".encode(), hashlib.sha256).hexdigest()
        self.assertFalse(verify_wave_signature(secret, f"t={ts},v1={signature}", body.encode()))


class PaymentWebhookRealTests(TestCase):
    """Webhooks Wave (HMAC) et Orange Money (notif_token) hors sandbox."""

    def setUp(self):
        self.client = APIClient()

    def _payment(self, metadata=None, method="wave"):
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        Role.objects.get_or_create(name=Role.RoleName.MERCHANT)
        merchant = User.objects.create_user(username="m@x.com", email="m@x.com", password="p", is_verified=True)
        UserRole.objects.create(user=merchant, role=Role.objects.get(name=Role.RoleName.MERCHANT))
        store = Store.objects.create(owner=merchant, name="Boutique")
        client = User.objects.create_user(username="c@x.com", email="c@x.com", password="p", is_verified=True)
        UserRole.objects.create(user=client, role=Role.objects.get(name=Role.RoleName.CLIENT))
        order = Order.objects.create(customer=client, store=store, total_amount=10000)
        return Payment.objects.create(order=order, amount=10000, method=method, metadata=metadata or {})

    def _wave_body(self, session_id, reference):
        return json.dumps({
            "id": "evt_1",
            "type": "checkout.session.completed",
            "data": {
                "id": session_id,
                "amount": "10000",
                "checkout_status": "complete",
                "client_reference": reference,
                "currency": "XOF",
                "payment_status": "succeeded",
            },
        })

    def _wave_header(self, secret, raw_body):
        ts = str(int(time.time()))
        signature = hmac.new(secret.encode(), f"{ts}{raw_body}".encode(), hashlib.sha256).hexdigest()
        return {"HTTP_WAVE_SIGNATURE": f"t={ts},v1={signature}"}

    @override_settings(PAYMENT_SANDBOX=False, PAYMENT_PROVIDERS={"wave": "whsec_test"})
    def test_wave_webhook_marks_payment_succeeded(self):
        payment = self._payment()
        raw = self._wave_body("cos-session", str(payment.id))
        response = self.client.post(
            "/api/payments/webhook/wave/", data=raw, content_type="application/json",
            **self._wave_header("whsec_test", raw),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        payment.order.refresh_from_db()
        self.assertEqual(payment.order.status, Order.Status.PAID)

    @override_settings(PAYMENT_SANDBOX=False, PAYMENT_PROVIDERS={"wave": "whsec_test"})
    def test_wave_webhook_rejects_bad_signature(self):
        payment = self._payment()
        raw = self._wave_body("cos-session", str(payment.id))
        response = self.client.post(
            "/api/payments/webhook/wave/", data=raw, content_type="application/json",
            **self._wave_header("wrong_secret", raw),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        payment.refresh_from_db()
        self.assertNotEqual(payment.status, Payment.Status.SUCCESS)

    @override_settings(PAYMENT_SANDBOX=False, PAYMENT_PROVIDERS={"wave": "whsec_test"})
    def test_wave_webhook_requires_configured_secret(self):
        payment = self._payment()
        raw = self._wave_body("cos-session", str(payment.id))
        with override_settings(PAYMENT_PROVIDERS={"wave": ""}):
            response = self.client.post(
                "/api/payments/webhook/wave/", data=raw, content_type="application/json",
                **self._wave_header("x", raw),
            )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        payment.refresh_from_db()
        self.assertNotEqual(payment.status, Payment.Status.SUCCESS)

    @override_settings(PAYMENT_SANDBOX=False, PAYMENT_PROVIDERS={"orange_money": ""})
    def test_orange_webhook_success_with_valid_notif_token(self):
        payment = self._payment(
            method="orange_money",
            metadata={"orange_money": {"order_id": "SM-ABC", "notif_token": "nt123", "pay_token": "p1"}},
        )
        response = self.client.post(
            "/api/payments/webhook/orange_money/",
            data=json.dumps({"status": "SUCCESS", "order_id": "SM-ABC", "notif_token": "nt123", "txnid": "txn1"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        payment.order.refresh_from_db()
        self.assertEqual(payment.order.status, Order.Status.PAID)

    @override_settings(PAYMENT_SANDBOX=False, PAYMENT_PROVIDERS={"orange_money": ""})
    def test_orange_webhook_rejects_wrong_notif_token(self):
        payment = self._payment(
            method="orange_money",
            metadata={"orange_money": {"order_id": "SM-ABC", "notif_token": "nt123", "pay_token": "p1"}},
        )
        response = self.client.post(
            "/api/payments/webhook/orange_money/",
            data=json.dumps({"status": "SUCCESS", "order_id": "SM-ABC", "notif_token": "WRONG", "txnid": "txn1"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        payment.refresh_from_db()
        self.assertNotEqual(payment.status, Payment.Status.SUCCESS)

    @override_settings(PAYMENT_SANDBOX=False, PAYMENT_PROVIDERS={"wave": "whsec_test"})
    def test_webhook_unknown_payment_returns_404(self):
        raw = self._wave_body("cos-unknown", "00000000-0000-0000-0000-000000000000")
        response = self.client.post(
            "/api/payments/webhook/wave/", data=raw, content_type="application/json",
            **self._wave_header("whsec_test", raw),
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(PAYMENT_SANDBOX=True)
    def test_sandbox_webhook_still_accepts_generic_format(self):
        payment = self._payment()
        response = self.client.post(
            "/api/payments/webhook/wave/",
            data=json.dumps({"reference": str(payment.id), "status": "success"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
