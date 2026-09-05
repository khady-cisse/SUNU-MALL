"""
Tests pour le paiement en mode sandbox : confirmation simulée, sécurité
d'accès (un client ne voit que ses propres paiements).
"""
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient
from apps.users.models import User, Role, UserRole
from apps.catalog.models import Store
from apps.orders.models import Order
from apps.payments.models import Payment


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
