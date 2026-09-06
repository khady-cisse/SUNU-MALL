"""
Tests du système de commission et du portefeuille vendeur (spec §30-§33).

Couvre : taux par plan, essai 0 %, backend seul (aucune confiance au client),
idempotence webhook, remboursement, libération, retrait avec KYC, multi-vendeurs.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import Product, ProductVariant, Store
from apps.commissions.models import (
    CommissionTransaction, Payout, PlatformWallet, SellerSubscription, SellerWallet,
)
from apps.commissions import services
from apps.kyc.models import SellerKYC
from apps.orders.models import Address, Delivery, Order, OrderItem
from apps.payments.models import Payment
from apps.users.models import Role, UserRole
from rest_framework.test import APIClient

User = get_user_model()


@override_settings(PAYMENT_SANDBOX=True)
class CommissionTestCase(TestCase):
    def setUp(self):
        Role.objects.get_or_create(name=Role.RoleName.MERCHANT)
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        Role.objects.get_or_create(name=Role.RoleName.ADMIN)
        self.seller = self.create_seller("seller@example.com")
        self.customer = self.create_customer("customer@example.com")

    # --- fabricants ---

    def create_user(self, email, role_name):
        user = User.objects.create_user(username=email, email=email, password="testpass123", is_verified=True)
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def create_seller(self, email):
        return self.create_user(email, Role.RoleName.MERCHANT)

    def create_customer(self, email):
        return self.create_user(email, Role.RoleName.CLIENT)

    def create_variant(self, sku, price, store=None):
        store = store or Store.objects.create(owner=self.seller, name=f"Store {sku}")
        return self.create_variant_for(sku, Decimal(price), store)

    def create_address(self):
        return Address.objects.create(
            user=self.customer, label="Domicile", city="Dakar",
            latitude=14.7167, longitude=-17.4677,
        )

    def make_paid_order(self, seller, items=None, variant=None):
        """Crée une commande payée (sandbox) pour `seller`, ventile la commission, retourne l'Order.

        `items` est une liste de (libellé, prix) ; chacun crée une ligne. Sans
        `items`, on crée une seule ligne de 10000 FCFA.
        """
        items = items or [("Article", "10000")]
        store_for = variant.product.store if variant else None
        if store_for is None:
            store_for = Store.objects.create(owner=seller, name=f"Store {seller.email}")
        line_items = []
        for label, price in items:
            sku = f"SKU-{abs(hash(label))}"
            v = variant or self.create_variant_for(sku, Decimal(price), store_for)
            line_items.append((v, Decimal(price)))

        address = self.create_address()
        order = Order.objects.create(
            customer=self.customer, store=store_for, address=address, delivery_fee=Decimal("200"),
        )
        total = Decimal("0")
        for v, price in line_items:
            OrderItem.objects.create(order=order, product_variant=v, quantity=1, unit_price=price)
            total += price
        order.total_amount = total + order.delivery_fee
        order.save(update_fields=["total_amount"])

        payment = Payment.objects.create(order=order, amount=order.total_amount, method="wave")
        payment.mark_succeeded()
        order.status = Order.Status.PAID
        order.save(update_fields=["status"])
        Delivery.objects.create(order=order)
        return order

    def create_variant_for(self, sku, price, store):
        product = Product.objects.create(store=store, name=f"Produit {sku}", base_price=price)
        return ProductVariant.objects.create(product=product, sku=sku, price=price)

    def payment_for(self, order):
        return Payment.objects.get(order=order)

    def refund_payment(self, order):
        from apps.payments.models import Refund
        payment = self.payment_for(order)
        refund = Refund.objects.create(
            payment=payment, amount=payment.amount, reason="Test",
            status=Refund.Status.COMPLETED, refunded_at=timezone.now(),
        )
        return refund

    def verify_seller_kyc(self, seller):
        SellerKYC.objects.create(
            seller=seller, status=SellerKYC.Status.VERIFIED,
            document_type="cni", document_front="kyc/seller/x/front.jpg",
            document_back="kyc/seller/x/back.jpg",
        )

    def _subscribe(self, seller, plan_name="BASIC"):
        entitlement = SellerSubscription.get_or_create_for(seller)
        now = timezone.now()
        entitlement.apply_paid_plan(plan_name, now - timedelta(days=1), now + timedelta(days=29))
        return entitlement


class CommissionTests(CommissionTestCase):
    def test_trial_rate_is_zero(self):
        order = self.make_paid_order(self.seller)
        tx = CommissionTransaction.objects.get(order=order)
        self.assertEqual(tx.commission_rate, Decimal("0"))
        self.assertEqual(tx.commission_amount, Decimal("0"))
        self.assertEqual(tx.seller_amount, order.total_amount)

    def test_plan_rate_applied_and_frozen(self):
        self._subscribe(self.seller, "BASIC")
        order = self.make_paid_order(self.seller)
        tx = CommissionTransaction.objects.get(order=order)
        expected_gross = order.total_amount - order.delivery_fee
        expected_commission = expected_gross * Decimal("0.05")
        self.assertEqual(tx.commission_rate, Decimal("5.00"))
        self.assertEqual(tx.commission_amount, expected_commission)
        self._subscribe(self.seller, "BUSINESS")
        tx.refresh_from_db()
        self.assertEqual(tx.commission_rate, Decimal("5.00"))

    def test_platform_wallet_credit_and_seller_pending(self):
        self._subscribe(self.seller, "PRO")
        order = self.make_paid_order(self.seller, items=[("Article PRO", "20000")])
        tx = CommissionTransaction.objects.get(order=order)
        wallet = SellerWallet.objects.get(seller=self.seller)
        platform = PlatformWallet.singleton()
        self.assertEqual(wallet.pending_balance, tx.seller_amount)
        self.assertEqual(wallet.available_balance, Decimal("0"))
        self.assertEqual(platform.total_commissions, tx.commission_amount)

    def test_settlement_is_idempotent(self):
        self._subscribe(self.seller, "BASIC")
        order = self.make_paid_order(self.seller)
        before = CommissionTransaction.objects.get(order=order)
        self.payment_for(order).mark_succeeded()
        self.assertEqual(CommissionTransaction.objects.filter(order=order, seller=self.seller).count(), 1)
        wallet = SellerWallet.objects.get(seller=self.seller)
        self.assertEqual(wallet.pending_balance, before.seller_amount)

    def test_gross_recomputed_from_db_not_client(self):
        self._subscribe(self.seller, "BASIC")
        order = self.make_paid_order(self.seller, items=[("Big", "10000"), ("Small", "5000")])
        order.total_amount = Decimal("99999")
        order.save(update_fields=["total_amount"])
        tx = CommissionTransaction.objects.get(order=order)
        expected_gross = Decimal("10000") + Decimal("5000")
        self.assertEqual(tx.gross_amount, expected_gross)
        self.assertEqual(tx.commission_amount, expected_gross * Decimal("0.05"))

    def test_refund_reverses_commission_and_seller_funds(self):
        self._subscribe(self.seller, "BASIC")
        order = self.make_paid_order(self.seller, items=[("A", "10000")])
        tx = CommissionTransaction.objects.get(order=order)
        wallet = SellerWallet.objects.get(seller=self.seller)
        self.assertEqual(wallet.pending_balance, tx.seller_amount)
        platform = PlatformWallet.singleton()
        commissions_before = platform.total_commissions

        refund = self.refund_payment(order)
        services.reverse_commission_for_refund(refund)

        tx.refresh_from_db()
        wallet.refresh_from_db()
        platform.refresh_from_db()
        self.assertTrue(tx.is_refunded)
        self.assertEqual(wallet.pending_balance, Decimal("0"))
        self.assertEqual(platform.total_commissions, commissions_before - tx.commission_amount)

    def test_refund_can_drive_wallet_negative_when_withdrawn(self):
        self._subscribe(self.seller, "BASIC")
        order = self.make_paid_order(self.seller, items=[("A", "10000")])
        tx = CommissionTransaction.objects.get(order=order)
        wallet = SellerWallet.objects.get(seller=self.seller)
        # Le vendeur a déjà retiré les fonds : plus rien dans le portefeuille.
        wallet.pending_balance = Decimal("0")
        wallet.available_balance = Decimal("0")
        wallet.total_withdrawn = tx.seller_amount
        wallet.save()

        refund = self.refund_payment(order)
        services.reverse_commission_for_refund(refund)
        wallet.refresh_from_db()
        self.assertEqual(wallet.available_balance, -tx.seller_amount)

    def test_release_moves_pending_to_available_after_delay(self):
        self._subscribe(self.seller, "BASIC")
        order = self.make_paid_order(self.seller)
        tx = CommissionTransaction.objects.get(order=order)
        wallet = SellerWallet.objects.get(seller=self.seller)
        self.assertEqual(wallet.pending_balance, tx.seller_amount)

        delivery = Delivery.objects.get(order=order)
        delivery.mark_delivered()
        delivery.delivered_at = timezone.now() - timedelta(days=settings.COMMISSION_RELEASE_DAYS + 1)
        delivery.save(update_fields=["delivered_at"])

        released = services.release_pending_funds(at=timezone.now())
        self.assertEqual(released, 1)
        wallet.refresh_from_db()
        tx.refresh_from_db()
        self.assertEqual(wallet.pending_balance, Decimal("0"))
        self.assertEqual(wallet.available_balance, tx.seller_amount)
        self.assertTrue(tx.is_released)

        self.assertEqual(services.release_pending_funds(at=timezone.now()), 0)

    def test_payout_requires_kyc_and_available_balance(self):
        self._subscribe(self.seller, "BASIC")
        with self.assertRaises(services.PayoutError):
            services.request_payout(self.seller, Decimal("100"))

        self.verify_seller_kyc(self.seller)
        self.make_paid_order(self.seller, items=[("A", "5000")])
        wallet = SellerWallet.objects.get(seller=self.seller)
        self.assertGreater(wallet.pending_balance, Decimal("0"))
        with self.assertRaises(services.PayoutError):
            services.request_payout(self.seller, Decimal("100"))

        wallet.pending_balance = Decimal("0")
        wallet.available_balance = Decimal("3000")
        wallet.save()
        payout = services.request_payout(self.seller, Decimal("2000"))
        self.assertEqual(payout.status, Payout.Status.PENDING)
        wallet.refresh_from_db()
        self.assertEqual(wallet.available_balance, Decimal("1000"))

        with self.assertRaises(services.PayoutError):
            services.request_payout(self.seller, Decimal("5000"))

    def test_unique_order_seller_prevents_duplicate(self):
        self._subscribe(self.seller, "BASIC")
        order = self.make_paid_order(self.seller)
        with self.assertRaises(Exception):
            CommissionTransaction.objects.create(
                order=order, seller=self.seller, plan="BASIC",
                gross_amount=Decimal("100"), commission_rate=Decimal("5"),
                commission_amount=Decimal("5"), seller_amount=Decimal("95"),
            )

    def test_gate_blocks_sales_after_grace_period(self):
        entitlement = SellerSubscription.get_or_create_for(self.seller)
        entitlement.status = SellerSubscription.Status.EXPIRED
        entitlement.plan = "BASIC"
        entitlement.trial_ends_at = timezone.now() - timedelta(days=40)
        entitlement.ends_at = timezone.now() - timedelta(days=40)
        entitlement.save()
        self.assertFalse(services.can_receive_orders(self.seller))

        entitlement.ends_at = timezone.now() - timedelta(days=2)
        entitlement.save()
        self.assertTrue(services.can_receive_orders(self.seller))

    def test_multiple_sellers_are_isolated(self):
        seller2 = self.create_seller("seller2@example.com")
        other_store = Store.objects.create(owner=seller2, name="Boutique 2")
        variant2 = self.create_variant("V2", "15000", store=other_store)
        self.make_paid_order(self.seller, items=[("A", "10000")])
        self.make_paid_order(seller2, variant=variant2, items=[("V2", "15000")])

        self._subscribe(self.seller, "BASIC")
        self._subscribe(seller2, "PRO")

        wallet1 = SellerWallet.objects.get(seller=self.seller)
        wallet2 = SellerWallet.objects.get(seller=seller2)
        tx1 = CommissionTransaction.objects.get(seller=self.seller)
        tx2 = CommissionTransaction.objects.get(seller=seller2)
        self.assertEqual(wallet1.pending_balance, tx1.seller_amount)
        self.assertEqual(wallet2.pending_balance, tx2.seller_amount)
        self.assertNotEqual(tx1.seller_amount, tx2.seller_amount)


class CommissionApiTests(CommissionTestCase):
    """Contrat REST : dashboard vendeur, journal commission (admin), retrait."""

    def setUp(self):
        super().setUp()
        self.admin = self.create_user("admin@example.com", Role.RoleName.ADMIN)
        self.client = APIClient()

    def _as(self, user):
        self.client.force_authenticate(user)
        return self.client

    def test_wallet_me_returns_balances_and_subscription(self):
        self._subscribe(self.seller, "BASIC")
        self.make_paid_order(self.seller, items=[("Dashboard", "10000")])
        response = self._as(self.seller).get("/api/commissions/wallet/me/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("wallet", data)
        self.assertEqual(data["subscription"]["plan"], "BASIC")
        self.assertEqual(data["subscription"]["status"], "active")
        self.assertEqual(len(data["recent_sales"]), 1)

    def test_subscription_me_exposes_trial_and_plans(self):
        response = self._as(self.seller).get("/api/commissions/subscription/me/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["subscription"]["status"], "trial")
        self.assertEqual(data["subscription"]["rate"], "0.00")

    def test_admin_commission_transactions_filtered(self):
        self._subscribe(self.seller, "BASIC")
        self.make_paid_order(self.seller, items=[("Filtré", "10000")])
        response = self._as(self.admin).get("/api/commissions/commissions/", {"plan": "BASIC"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        # Un commerçant ne voit que ses propres ventes.
        response = self._as(self.seller).get("/api/commissions/commissions/")
        self.assertEqual(response.status_code, 200)

    def test_admin_stats_endpoint(self):
        self._subscribe(self.seller, "PRO")
        self.make_paid_order(self.seller, items=[("Stats", "20000")])
        response = self._as(self.admin).get("/api/commissions/commissions/stats/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_commissions"], "600.00")

    def test_payout_flow_end_to_end(self):
        # Vente réglée → livrée → libérée → le vendeur retire de son solde disponible.
        self._subscribe(self.seller, "BASIC")
        self.verify_seller_kyc(self.seller)
        order = self.make_paid_order(self.seller, items=[("Retrait", "20000")])
        delivery = Delivery.objects.get(order=order)
        delivery.mark_delivered()
        delivery.delivered_at = timezone.now() - timedelta(days=settings.COMMISSION_RELEASE_DAYS + 1)
        delivery.save(update_fields=["delivered_at"])
        services.release_pending_funds(at=timezone.now())

        wallet = SellerWallet.objects.get(seller=self.seller)
        self.assertGreater(wallet.available_balance, Decimal("0"))
        available_before = wallet.available_balance

        response = self._as(self.seller).post(
            "/api/commissions/payouts/",
            {"amount": "1000", "method": "wave"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        payout_id = response.json()["id"]
        wallet.refresh_from_db()
        self.assertEqual(wallet.available_balance, available_before - Decimal("1000"))
        self.assertGreaterEqual(wallet.total_withdrawn, Decimal("1000"))

        # L'admin approuve le retrait.
        response = self._as(self.admin).post(f"/api/commissions/payouts/{payout_id}/approve/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")