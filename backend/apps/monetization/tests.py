"""
Tests de la monétisation SUNU MALL (spec §24-§25).

Couvre : les 3 plans, les limites de produits (Starter 10 / Pro 30 /
Business illimité), le premier mois gratuit, le cycle de vie de l'abonnement
(création, activation, renouvellement, changement de plan, expiration,
annulation), les références SUB-YYYYMMDD-######, les paiements (webhook,
doublons, référence unique), les permissions (un vendeur ne voit jamais
l'abonnement/l'historique/paiements d'un autre), et le gating KYC.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductVariant, Store
from apps.commissions.models import SellerSubscription as CommissionSubscription
from apps.commissions.services import can_receive_orders
from apps.kyc.models import SellerKYC
from apps.monetization.models import (
    Invoice, Subscription, SubscriptionHistory, SubscriptionPlan,
)
from apps.monetization import services
from apps.payments.models import Payment
from apps.users.models import Role, UserRole

User = get_user_model()

SEEDED_PLANS = [
    {"code": "STARTER", "name": "STARTER", "price": 2500, "max_products": 10},
    {"code": "PRO", "name": "PRO", "price": 5000, "max_products": 30},
    {"code": "BUSINESS", "name": "BUSINESS", "price": 10000, "max_products": None},
]


def _seed_plans():
    for plan in SEEDED_PLANS:
        SubscriptionPlan.objects.update_or_create(
            code=plan["code"],
            defaults={
                "name": plan["name"],
                "price": plan["price"],
                "billing_cycle": "monthly",
                "features": {"produits": "x"},
                "max_products": plan["max_products"],
                "commission_rate": "0.00",
                "duration_days": 30,
                "is_active": True,
            },
        )


class MonetizationTestCase(TestCase):
    def setUp(self):
        Role.objects.get_or_create(name=Role.RoleName.MERCHANT)
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        Role.objects.get_or_create(name=Role.RoleName.ADMIN)
        _seed_plans()
        self.client = APIClient()
        self.seller = self.create_seller("seller@example.com")
        self.other_seller = self.create_seller("other@example.com")
        self.customer = self.create_customer("customer@example.com")

    # --- fabricants ---

    def create_user(self, email, role_name):
        user = User.objects.create_user(
            username=email, email=email, password="testpass123", is_verified=True
        )
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def create_seller(self, email):
        return self.create_user(email, Role.RoleName.MERCHANT)

    def create_customer(self, email):
        return self.create_user(email, Role.RoleName.CLIENT)

    def verify_seller_kyc(self, seller):
        SellerKYC.objects.create(
            seller=seller, status=SellerKYC.Status.VERIFIED,
            document_type="cni", document_front="kyc/seller/x/front.jpg",
            document_back="kyc/seller/x/back.jpg",
        )

    def get_plan(self, code):
        return SubscriptionPlan.objects.get(code=code)

    def get_latest_subscription(self, seller):
        """Dernière souscription du vendeur (les PK sont des UUID : on trie
        par created_at, jamais par id)."""
        return Subscription.objects.filter(subscriber_id=seller.id).order_by("-created_at").first()

    def create_store(self, owner, name="Ma Boutique"):
        return Store.objects.create(owner=owner, name=name)

    def create_products(self, seller, n, store=None):
        store = store or self.create_store(seller)
        products = []
        for i in range(n):
            p = Product.objects.create(store=store, name=f"Produit {i}", base_price=Decimal("1000"))
            ProductVariant.objects.create(product=p, sku=f"SKU-{i}", price=Decimal("1000"))
            products.append(p)
        return products

    def give_prior_subscription(self, seller, code="STARTER", status=Subscription.Status.EXPIRED):
        """Historique d'abonnement antérieur : la prochaine souscription n'est
        plus éligible au premier mois gratuit (elle passe donc par le paiement)."""
        plan = self.get_plan(code)
        today = timezone.now().date()
        return Subscription.objects.create(
            plan=plan, subscriber_type="merchant", subscriber_id=seller.id,
            status=status,
            starts_at=today - timedelta(days=30), ends_at=today - timedelta(days=1),
        )


class PlanTests(MonetizationTestCase):
    def test_three_active_plans_exist(self):
        plans = SubscriptionPlan.objects.filter(is_active=True)
        self.assertEqual(plans.count(), 3)

    def test_prices_are_correct(self):
        self.assertEqual(self.get_plan("STARTER").price, Decimal("2500"))
        self.assertEqual(self.get_plan("PRO").price, Decimal("5000"))
        self.assertEqual(self.get_plan("BUSINESS").price, Decimal("10000"))

    def test_product_limits(self):
        self.assertEqual(self.get_plan("STARTER").max_products, 10)
        self.assertEqual(self.get_plan("PRO").max_products, 30)
        self.assertIsNone(self.get_plan("BUSINESS").max_products)

    def test_commission_is_zero_for_all_plans(self):
        for plan in SubscriptionPlan.objects.all():
            self.assertEqual(plan.commission_rate, Decimal("0"))


class SubscriptionLifecycleTests(MonetizationTestCase):
    def test_creation_is_pending_with_dates(self):
        resp = self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('PRO').id}/subscribe/",
            {"payment_method": "wave"},
        )
        # Non authentifié → 401
        self.assertEqual(resp.status_code, 401)

    def test_subscribe_creates_pending_subscription_and_payment(self):
        self.give_prior_subscription(self.seller)
        self.client.force_authenticate(self.seller)
        resp = self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('PRO').id}/subscribe/",
            {"payment_method": "wave"},
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        self.assertEqual(data["subscription"]["status"], Subscription.Status.PENDING)
        self.assertIsNotNone(data["payment"])
        self.assertEqual(data["payment"]["status"], Payment.Status.PENDING)
        self.assertTrue(Subscription.objects.filter(subscriber_id=self.seller.id).exists())

    def test_two_active_subscriptions_not_allowed(self):
        self.client.force_authenticate(self.seller)
        self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('PRO').id}/subscribe/",
            {"payment_method": "wave"},
        )
        resp = self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('STARTER').id}/subscribe/",
            {"payment_method": "wave"},
        )
        self.assertIn(resp.status_code, (400, 409))

    def test_activation_only_after_backend_confirmation(self):
        self.give_prior_subscription(self.seller)
        self.client.force_authenticate(self.seller)
        resp = self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('STARTER').id}/subscribe/",
            {"payment_method": "wave"},
        )
        payment_id = resp.json()["payment"]["id"]
        sub = self.get_latest_subscription(self.seller)
        self.assertEqual(sub.status, Subscription.Status.PENDING)
        # Pas encore actif tant que le backend ne confirme pas.
        self.assertIsNone(services.active_subscription(self.seller))

        payment = Payment.objects.get(id=payment_id)
        payment.mark_succeeded()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertIsNotNone(services.active_subscription(self.seller))
        # Historique d'activation créé.
        self.assertTrue(
            SubscriptionHistory.objects.filter(
                subscription=sub, action=SubscriptionHistory.Action.ACTIVATED
            ).exists()
        )

    def test_renewal_extends_end_date(self):
        self.give_prior_subscription(self.seller)
        self.client.force_authenticate(self.seller)
        resp = self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('PRO').id}/subscribe/",
            {"payment_method": "wave"},
        )
        sub = self.get_latest_subscription(self.seller)
        # Confirmer le paiement de souscription en attente (plus de paiement bloquant).
        Payment.objects.get(id=resp.json()["payment"]["id"]).mark_succeeded()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        original_end = sub.ends_at

        resp = self.client.post("/api/monetization/subscription/renew/", {"payment_method": "wave"})
        self.assertEqual(resp.status_code, 201, resp.content)
        payment = Payment.objects.get(id=resp.json()["payment"]["id"])
        payment.mark_succeeded()
        sub.refresh_from_db()
        self.assertEqual(sub.ends_at, original_end + timedelta(days=30))

    def test_change_plan(self):
        self.give_prior_subscription(self.seller)
        self.client.force_authenticate(self.seller)
        resp = self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('STARTER').id}/subscribe/",
            {"payment_method": "wave"},
        )
        sub = self.get_latest_subscription(self.seller)
        Payment.objects.get(id=resp.json()["payment"]["id"]).mark_succeeded()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)

        resp = self.client.post(
            "/api/monetization/subscription/change-plan/", {"plan_code": "PRO", "payment_method": "wave"}
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        payment = Payment.objects.get(id=resp.json()["payment"]["id"])
        payment.mark_succeeded()
        sub.refresh_from_db()
        self.assertEqual(sub.plan.code, "PRO")
        self.assertTrue(
            SubscriptionHistory.objects.filter(
                subscription=sub, action=SubscriptionHistory.Action.PLAN_CHANGED,
                old_plan_id=self.get_plan("STARTER").id, new_plan_id=self.get_plan("PRO").id,
            ).exists()
        )

    def test_cancel(self):
        self.give_prior_subscription(self.seller)
        self.client.force_authenticate(self.seller)
        self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('STARTER').id}/subscribe/",
            {"payment_method": "wave"},
        )
        sub = self.get_latest_subscription(self.seller)
        resp = self.client.post(f"/api/monetization/subscriptions/{sub.id}/cancel/")
        self.assertEqual(resp.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CANCELLED)

    def test_can_receive_orders_requires_active_subscription(self):
        self.verify_seller_kyc(self.seller)
        ent = CommissionSubscription.get_or_create_for(self.seller)
        # KYC vérifié mais abonnement hors essai/grâce → ne peut pas vendre.
        ent.status = CommissionSubscription.Status.EXPIRED
        ent.trial_ends_at = timezone.now() - timedelta(days=40)
        ent.ends_at = timezone.now() - timedelta(days=40)
        ent.save()
        self.assertFalse(can_receive_orders(self.seller))

        # Plan actif → autorisé.
        now = timezone.now()
        ent.apply_paid_plan("STARTER", now - timedelta(days=1), now + timedelta(days=29))
        self.assertTrue(can_receive_orders(self.seller))

    def test_expiration_via_task(self):
        self.give_prior_subscription(self.seller)
        self.client.force_authenticate(self.seller)
        self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('STARTER').id}/subscribe/",
            {"payment_method": "wave"},
        )
        sub = self.get_latest_subscription(self.seller)
        sub.status = Subscription.Status.ACTIVE
        sub.ends_at = timezone.now().date() - timedelta(days=1)
        sub.save()

        from apps.monetization.tasks import expire_and_remind_subscriptions
        expire_and_remind_subscriptions()
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.EXPIRED)
        self.assertTrue(
            SubscriptionHistory.objects.filter(
                subscription=sub, action=SubscriptionHistory.Action.EXPIRED
            ).exists()
        )


class ProductLimitTests(MonetizationTestCase):
    def _subscribe_active(self, code):
        self.client.force_authenticate(self.seller)
        plan = self.get_plan(code)
        self.client.post(
            f"/api/monetization/subscription-plans/{plan.id}/subscribe/",
            {"payment_method": "wave"},
        )
        sub = self.get_latest_subscription(self.seller)
        sub.status = Subscription.Status.ACTIVE
        sub.save(update_fields=["status"])
        return sub

    def test_starter_blocks_at_plan_limit(self):
        self._subscribe_active("STARTER")
        store = self.create_store(self.seller)
        self.create_products(self.seller, 10, store)
        self.assertEqual(Product.objects.filter(store=store).count(), 10)
        with self.assertRaises(Exception):
            services.check_product_creation_allowed(self.seller)

    def test_pro_blocks_at_plan_limit(self):
        self._subscribe_active("PRO")
        store = self.create_store(self.seller)
        self.create_products(self.seller, 30, store)
        self.assertEqual(Product.objects.filter(store=store).count(), 30)
        with self.assertRaises(Exception):
            services.check_product_creation_allowed(self.seller)

    def test_business_is_unlimited(self):
        self._subscribe_active("BUSINESS")
        store = self.create_store(self.seller)
        self.create_products(self.seller, 150, store)
        self.assertIsNone(services.product_limit_for(self.seller))
        services.check_product_creation_allowed(self.seller)

    def test_no_active_subscription_blocks(self):
        # Forcer l'entitlement commission hors essai/grâce → bloqué.
        ent = CommissionSubscription.get_or_create_for(self.seller)
        ent.status = CommissionSubscription.Status.EXPIRED
        ent.trial_ends_at = timezone.now() - timedelta(days=40)
        ent.ends_at = timezone.now() - timedelta(days=40)
        ent.save()
        self.assertEqual(services.product_limit_for(self.seller), 0)
        with self.assertRaises(Exception):
            services.check_product_creation_allowed(self.seller)


class FirstMonthFreeTests(MonetizationTestCase):
    def test_first_subscription_is_free_and_immediately_active(self):
        self.client.force_authenticate(self.seller)
        resp = self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('PRO').id}/subscribe/",
            {"payment_method": "wave"},
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        self.assertEqual(data["promo"], "first_month_free")
        self.assertIsNone(data["payment"])
        self.assertEqual(data["subscription"]["status"], Subscription.Status.ACTIVE)
        sub = self.get_latest_subscription(self.seller)
        self.assertTrue(sub.is_active())
        # L'historique trace la promotion (preuve métier).
        self.assertTrue(
            SubscriptionHistory.objects.filter(
                subscription=sub, action=SubscriptionHistory.Action.ACTIVATED,
                metadata__promo="first_month_free",
            ).exists()
        )

    def test_second_subscription_is_charged_after_expiry(self):
        self.client.force_authenticate(self.seller)
        resp = self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('PRO').id}/subscribe/",
            {"payment_method": "wave"},
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        sub = self.get_latest_subscription(self.seller)
        sub.status = Subscription.Status.EXPIRED
        sub.ends_at = timezone.now().date() - timedelta(days=1)
        sub.save(update_fields=["status", "ends_at"])

        resp = self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('STARTER').id}/subscribe/",
            {"payment_method": "wave"},
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        self.assertIsNone(data.get("promo"))
        self.assertIsNotNone(data["payment"])
        self.assertEqual(data["subscription"]["status"], Subscription.Status.PENDING)


class SubscriptionReferenceTests(MonetizationTestCase):
    def test_reference_is_generated_with_spec_format(self):
        sub = Subscription.objects.create(
            plan=self.get_plan("STARTER"), subscriber_type="merchant", subscriber_id=self.seller.id,
            starts_at=timezone.now().date(), ends_at=timezone.now().date() + timedelta(days=30),
        )
        self.assertRegex(sub.reference, r"^SUB-\d{8}-[0-9A-F]{6}$")

    def test_references_are_unique_across_subscriptions(self):
        sub = Subscription.objects.create(
            plan=self.get_plan("STARTER"), subscriber_type="merchant", subscriber_id=self.seller.id,
            starts_at=timezone.now().date(), ends_at=timezone.now().date() + timedelta(days=30),
        )
        other = Subscription.objects.create(
            plan=self.get_plan("PRO"), subscriber_type="merchant", subscriber_id=self.other_seller.id,
            starts_at=timezone.now().date(), ends_at=timezone.now().date() + timedelta(days=30),
        )
        self.assertNotEqual(sub.reference, other.reference)
        self.assertEqual(Subscription.objects.filter(reference__isnull=True).count(), 0)

    def test_reference_exposed_on_subscribe_response(self):
        self.client.force_authenticate(self.seller)
        resp = self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('STARTER').id}/subscribe/",
            {"payment_method": "wave"},
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        reference = resp.json()["subscription"]["reference"]
        self.assertRegex(reference, r"^SUB-\d{8}-[0-9A-F]{6}$")


class PaymentWebhookTests(MonetizationTestCase):
    def setUp(self):
        super().setUp()
        self.give_prior_subscription(self.seller)
    @override_settings(PAYMENT_SANDBOX=True)
    def test_webhook_success_activates_subscription(self):
        self.client.force_authenticate(self.seller)
        resp = self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('PRO').id}/subscribe/",
            {"payment_method": "wave"},
        )
        payment = Payment.objects.get(id=resp.json()["payment"]["id"])

        wb = self.client.post(
            "/api/payments/webhook/wave/",
            {"reference": str(payment.id), "status": "success"},
            format="json",
        )
        self.assertEqual(wb.status_code, 200, wb.content)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertEqual(payment.subscription.status, Subscription.Status.ACTIVE)

    @override_settings(PAYMENT_SANDBOX=True)
    def test_webhook_duplicate_does_not_double_activate(self):
        self.client.force_authenticate(self.seller)
        resp = self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('PRO').id}/subscribe/",
            {"payment_method": "wave"},
        )
        payment = Payment.objects.get(id=resp.json()["payment"]["id"])
        sub = payment.subscription
        sub.status = Subscription.Status.ACTIVE
        sub.save(update_fields=["status"])
        original_end = sub.ends_at

        for _ in range(3):
            wb = self.client.post(
                "/api/payments/webhook/wave/",
                {"reference": str(payment.id), "status": "success"},
                format="json",
            )
            self.assertEqual(wb.status_code, 200)
        sub.refresh_from_db()
        # Pas de double allongement.
        self.assertEqual(sub.ends_at, original_end)
        # Une seule facture.
        self.assertEqual(Invoice.objects.filter(subscription=sub).count(), 1)

    @override_settings(PAYMENT_SANDBOX=True)
    def test_webhook_failure_marks_failed(self):
        self.client.force_authenticate(self.seller)
        resp = self.client.post(
            f"/api/monetization/subscription-plans/{self.get_plan('PRO').id}/subscribe/",
            {"payment_method": "wave"},
        )
        payment = Payment.objects.get(id=resp.json()["payment"]["id"])
        wb = self.client.post(
            "/api/payments/webhook/wave/",
            {"reference": str(payment.id), "status": "failed"},
            format="json",
        )
        self.assertEqual(wb.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)

    @override_settings(PAYMENT_SANDBOX=True)
    def test_unknown_reference_rejected(self):
        wb = self.client.post(
            "/api/payments/webhook/wave/",
            {"reference": "unknown-ref-123", "status": "success"},
            format="json",
        )
        self.assertEqual(wb.status_code, 404)


class PermissionTests(MonetizationTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _subscribe(self, seller, code):
        plan = self.get_plan(code)
        sub = Subscription.objects.create(
            plan=plan, subscriber_type="merchant", subscriber_id=seller.id,
            starts_at=timezone.now().date(), ends_at=timezone.now().date() + timedelta(days=30),
            status=Subscription.Status.ACTIVE,
        )
        return sub

    def test_seller_cannot_produce_payment_for_other(self):
        other_sub = self._subscribe(self.other_seller, "STARTER")
        payment = Payment.objects.create(
            subscription=other_sub, amount=Decimal("2500"), currency="XOF", method="wave",
        )
        self.client.force_authenticate(self.seller)
        resp = self.client.get(f"/api/payments/{payment.id}/")
        self.assertEqual(resp.status_code, 404)

    def test_seller_cannot_see_other_subscription_via_me(self):
        self._subscribe(self.other_seller, "PRO")
        self.client.force_authenticate(self.seller)
        resp = self.client.get("/api/monetization/subscription/me/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["subscription"])

    def test_history_is_scoped_to_owner(self):
        self._subscribe(self.other_seller, "STARTER")
        sub = Subscription.objects.get(subscriber_id=self.other_seller.id)
        SubscriptionHistory.objects.create(
            subscription=sub, seller=self.other_seller, action=SubscriptionHistory.Action.ACTIVATED,
        )
        self.client.force_authenticate(self.seller)
        resp = self.client.get("/api/monetization/subscription/history/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 0)

    def test_change_plan_requires_own_subscription(self):
        self._subscribe(self.other_seller, "STARTER")
        self.client.force_authenticate(self.seller)
        resp = self.client.post(
            "/api/monetization/subscription/change-plan/", {"plan_code": "PRO"}
        )
        # Pas d'abonnement à modifier pour ce vendeur.
        self.assertEqual(resp.status_code, 400)


class KycGatingTests(MonetizationTestCase):
    def test_non_verified_seller_cannot_receive_orders(self):
        # KYC non vérifié → can_receive_orders False, quel que soit l'abonnement.
        CommissionSubscription.get_or_create_for(self.seller)
        self.assertFalse(can_receive_orders(self.seller))

    def test_verified_seller_with_active_subscription_can(self):
        self.verify_seller_kyc(self.seller)
        self._subscribe_active_commission(self.seller)
        self.assertTrue(can_receive_orders(self.seller))

    def _subscribe_active_commission(self, seller):
        ent = CommissionSubscription.get_or_create_for(seller)
        now = timezone.now()
        ent.apply_paid_plan("STARTER", now - timedelta(days=1), now + timedelta(days=29))
        return ent


class NotificationBroadcastTests(MonetizationTestCase):
    def test_admin_broadcasts_to_all_and_logs(self):
        from apps.monetization.models import Notification
        from apps.security.models import AdminAuditLog

        admin = self.create_user("admin@example.com", Role.RoleName.ADMIN)
        self.client.force_authenticate(admin)
        resp = self.client.post(
            "/api/monetization/notifications/broadcast/",
            {"subject": "Maintenance SAMEDI", "message": "Plateforme indisponible 00h-02h."},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["sent"], User.objects.filter(is_active=True).count())
        all_users = User.objects.filter(
            is_active=True, notifications__subject="Maintenance SAMEDI"
        ).distinct()
        self.assertEqual(all_users.count(), User.objects.filter(is_active=True).count())
        self.assertTrue(AdminAuditLog.objects.filter(
            admin=admin, object_type="Notification",
        ).exists())

    def test_broadcast_scoped_to_role(self):
        from apps.monetization.models import Notification

        admin = self.create_user("admin@example.com", Role.RoleName.ADMIN)
        self.client.force_authenticate(admin)
        resp = self.client.post(
            "/api/monetization/notifications/broadcast/",
            {"subject": "Offre spéciale vendeurs",
             "message": "Promotion sur le plan PRO.",
             "role": Role.RoleName.MERCHANT},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["role"], Role.RoleName.MERCHANT)
        for user in User.objects.filter(user_roles__role__name=Role.RoleName.MERCHANT):
            self.assertTrue(user.notifications.filter(subject="Offre spéciale vendeurs").exists())
        self.assertFalse(self.customer.notifications.filter(subject="Offre spéciale vendeurs").exists())

    def test_non_admin_cannot_broadcast(self):
        self.client.force_authenticate(self.customer)
        resp = self.client.post(
            "/api/monetization/notifications/broadcast/",
            {"subject": "Interdit", "message": "Doit échouer"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_broadcast_requires_subject_and_message(self):
        admin = self.create_user("admin@example.com", Role.RoleName.ADMIN)
        self.client.force_authenticate(admin)
        resp = self.client.post(
            "/api/monetization/notifications/broadcast/",
            {"subject": "", "message": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
