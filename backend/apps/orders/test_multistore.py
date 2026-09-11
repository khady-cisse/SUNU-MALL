"""
Tests de la commande multi-boutiques (spec multi-boutiques).

Couvre :
- le moteur de tarification (base, points de collecte, express, min/max) ;
- l'endpoint de calcul pré-paiement `delivery-calculate` ;
- le passage de commande global (GlobalOrder + sous-commandes + pickups +
  paiement global unique + nettoyage du panier) ;
- l'isolation entre vendeurs (spec §11) ;
- la collecte progressive des points (livreur) ;
- la confirmation du paiement global (idempotente).
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import Inventory, Product, ProductVariant, Store
from apps.orders.geoutils import haversine_km
from apps.orders.models import (
    Address, Delivery, DeliveryPickup, DeliveryPricingRule, Driver, GlobalOrder,
    Order, OrderItem,
)
from apps.orders.pricing import compute_delivery_fee_multi, route_distance_km
from apps.payments.models import Payment, Transaction
from apps.shopping.models import Cart, CartItem
from apps.users.models import Role, UserRole

User = get_user_model()

SENEGAL_CENTER = (Decimal("14.716677"), Decimal("-17.467686"))


class MultiStoreTestMixin:
    def setUp(self):
        for role_name in (Role.RoleName.MERCHANT, Role.RoleName.CLIENT, Role.RoleName.DRIVER):
            Role.objects.get_or_create(name=role_name)

        self.client = APIClient()
        self.customer = self._make_user("client@example.com", Role.RoleName.CLIENT)
        self.merchant_a = self._make_user("seller-a@example.com", Role.RoleName.MERCHANT)
        self.merchant_b = self._make_user("seller-b@example.com", Role.RoleName.MERCHANT)
        self.driver_user = self._make_user("driver@example.com", Role.RoleName.DRIVER)

        self.store_a = self._make_store(
            self.merchant_a, "Boutique A", Decimal("14.7350"), Decimal("-17.4380")
        )
        self.store_b = self._make_store(
            self.merchant_b, "Boutique B", Decimal("14.7450"), Decimal("-17.5280")
        )

        self.variant_a = self._make_variant(self.store_a, "SKU-A", Decimal("2000"))
        self.variant_b = self._make_variant(self.store_b, "SKU-B", Decimal("1500"))

        self.address = Address.objects.create(
            user=self.customer, label="Domicile", city="Dakar",
            latitude=14.7167, longitude=-17.4677,
        )

        self.driver = Driver.objects.create(
            user=self.driver_user,
            availability_status=Driver.AvailabilityStatus.AVAILABLE,
            last_latitude=self.store_a.latitude,
            last_longitude=self.store_a.longitude,
            is_suspended=False,
        )

        cart = Cart.objects.create(user=self.customer)
        cart.add_item(self.variant_a, 1)
        cart.add_item(self.variant_b, 2)

    # --- fabricants ---

    def _make_user(self, email, role_name):
        user = User.objects.create_user(username=email, email=email, password="testpass123", is_verified=True)
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def _make_store(self, owner, name, lat, lng):
        return Store.objects.create(
            owner=owner, name=name, status=Store.Status.ACTIVE,
            address=f"{name}, Dakar", city="Dakar",
            latitude=lat, longitude=lng,
        )

    def _make_variant(self, store, sku, price):
        product = Product.objects.create(
            store=store, name=f"Produit {sku}", base_price=price, status=Product.Status.ACTIVE,
        )
        variant = ProductVariant.objects.create(product=product, sku=sku, price=price)
        Inventory.objects.create(variant=variant, quantity=20)
        return variant

    def _checkout_payload(self, variant_ids=None, delivery_type="standard"):
        variants = variant_ids or [str(self.variant_a.id), str(self.variant_b.id)]
        items = [{"product_variant": variants[0], "quantity": 1}]
        if len(variants) > 1:
            items.append({"product_variant": variants[1], "quantity": 1})
        return {
            "address": str(self.address.id),
            "delivery_type": delivery_type,
            "payment_method": "wave",
            "items": items,
        }

    def _perform_checkout(self, **overrides):
        payload = self._checkout_payload()
        payload.update(overrides)
        self.client.force_authenticate(self.customer)
        return self.client.post("/api/orders/checkout/", payload, format="json")


class PricingMultiStoreTests(TestCase):
    """Tarification : les montants viennent de DeliveryPricingRule (jamais de
    constantes dans le moteur), base + points de collecte + km + express, bornes."""

    def setUp(self):
        for role_name in (Role.RoleName.MERCHANT, Role.RoleName.CLIENT):
            Role.objects.get_or_create(name=role_name)
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com",
                                         password="testpass123", is_verified=True)
        role = Role.objects.get(name=Role.RoleName.MERCHANT)
        UserRole.objects.create(user=owner, role=role)
        customer = User.objects.create_user(username="co@example.com", email="co@example.com",
                                            password="testpass123", is_verified=True)
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        role_c = Role.objects.get(name=Role.RoleName.CLIENT)
        UserRole.objects.create(user=customer, role=role_c)

        lat, lng = SENEGAL_CENTER
        self.store = Store.objects.create(owner=owner, name="Boutique", status=Store.Status.ACTIVE,
                                          latitude=lat, longitude=lng)
        self.other = Store.objects.create(owner=owner, name="Boutique #2", status=Store.Status.ACTIVE,
                                          latitude=lat, longitude=lng)
        self.address = Address.objects.create(user=customer, label="Domicile", city="Dakar",
                                              latitude=float(lat), longitude=float(lng))

    def _rule(self, **kwargs):
        defaults = dict(name="Règle de test", is_active=True,
                        base_fee=Decimal("1500"), extra_pickup_fee=Decimal("800"),
                        per_km_fee=Decimal("150"), express_surcharge=Decimal("800"),
                        min_fee=Decimal("1000"), max_fee=None)
        defaults.update(kwargs)
        DeliveryPricingRule.objects.filter(is_active=True).update(is_active=False)
        return DeliveryPricingRule.objects.create(**defaults)

    def test_one_store_base_fee(self):
        self._rule()
        fee = compute_delivery_fee_multi([self.store], self.address, "standard")
        self.assertEqual(fee, Decimal("1500"))

    def test_each_store_adds_extra_pickup_fee(self):
        self._rule()
        fee_1 = compute_delivery_fee_multi([self.store], self.address, "standard")
        fee_2 = compute_delivery_fee_multi([self.store, self.other], self.address, "standard")
        self.assertEqual(fee_2 - fee_1, Decimal("800"))

    def test_three_stores_charges_two_pickups(self):
        self._rule()
        third = Store.objects.create(owner=self.store.owner, name="Boutique #3",
                                     status=Store.Status.ACTIVE, latitude=self.store.latitude,
                                     longitude=self.store.longitude)
        fee_2 = compute_delivery_fee_multi([self.store, self.other], self.address, "standard")
        fee_3 = compute_delivery_fee_multi([self.store, self.other, third], self.address, "standard")
        self.assertEqual(fee_3 - fee_2, Decimal("800"))

    def test_express_adds_surcharge(self):
        rule = self._rule()
        standard = compute_delivery_fee_multi([self.store], self.address, "standard")
        express = compute_delivery_fee_multi([self.store], self.address, "express", total_weight=None)
        self.assertEqual(express - standard, rule.express_surcharge)

    def test_min_fee_is_the_floor(self):
        self._rule(min_fee=Decimal("5000"))
        fee = compute_delivery_fee_multi([self.store], self.address, "standard")
        self.assertEqual(fee, Decimal("5000"))

    def test_route_distance_is_robust_to_store_order(self):
        self._rule()
        a = Store.objects.create(owner=self.store.owner, name="A", status=Store.Status.ACTIVE,
                                 latitude=Decimal("14.7500"), longitude=Decimal("-17.4500"))
        b = Store.objects.create(owner=self.store.owner, name="B", status=Store.Status.ACTIVE,
                                 latitude=Decimal("14.7000"), longitude=Decimal("-17.4800"))
        d_ab = route_distance_km([a, b], self.address.latitude, self.address.longitude)
        d_ba = route_distance_km([b, a], self.address.latitude, self.address.longitude)
        self.assertEqual(d_ab, d_ba)
        haversine_ab = haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)
        self.assertGreater(d_ab, Decimal(str(haversine_ab)))


class MultiStorePricingApiTests(MultiStoreTestMixin, TestCase):
    def test_delivery_calculate_returns_quote(self):
        self.client.force_authenticate(self.customer)
        payload = self._checkout_payload()
        response = self.client.post("/api/orders/delivery-calculate/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["number_of_stores"], 2)
        self.assertEqual(response.data["number_of_pickups"], 2)
        self.assertEqual(response.data["currency"], "XOF")
        self.assertGreater(float(response.data["delivery_fee"]), 0)
        self.assertIsNotNone(response.data["distance"])

    def test_delivery_calculate_rejects_unknown_variant(self):
        self.client.force_authenticate(self.customer)
        payload = self._checkout_payload([str(self.variant_a.id), "00000000-0000-0000-0000-000000000000"])
        response = self.client.post("/api/orders/delivery-calculate/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@patch("apps.commissions.services.can_receive_orders", return_value=True)
class MultiStoreCheckoutFlowTests(MultiStoreTestMixin, TestCase):
    def test_checkout_creates_global_order_and_children(self, _can_receive):
        response = self._perform_checkout()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["reference"].startswith("SM-"))
        self.assertEqual(response.data["number_of_stores"], 2)
        self.assertEqual(response.data["status"], GlobalOrder.Status.PENDING)

        global_order = GlobalOrder.objects.get(pk=response.data["id"])
        orders = list(global_order.orders.all())
        self.assertEqual(len(orders), 2)
        self.assertEqual({o.store_id for o in orders}, {self.store_a.id, self.store_b.id})
        for order in orders:
            self.assertEqual(order.global_order_id, global_order.id)
            self.assertEqual(order.total_amount, sum(i.subtotal() for i in order.items.all()))

        delivery = global_order.deliveries.first()
        self.assertIsNotNone(delivery)
        self.assertTrue(delivery.is_multi_store)
        self.assertIsNone(delivery.order)
        pickups = list(delivery.pickups.all())
        self.assertEqual(len(pickups), 2)
        self.assertEqual({p.store_id for p in pickups}, {self.store_a.id, self.store_b.id})
        self.assertEqual({p.pickup_order for p in pickups}, {1, 2})
        self.assertEqual(delivery.total_delivery_fee, global_order.delivery_fee)
        self.assertEqual(delivery.platform_margin, global_order.delivery_fee)
        self.assertEqual(delivery.partner_cost, 0)

        payment = global_order.payments.first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.global_order_id, global_order.id)
        self.assertEqual(payment.amount, global_order.total_amount)

        self.assertFalse(CartItem.objects.filter(cart__user=self.customer).exists())

    def test_checkout_multistore_applies_express_surcharge(self, _can_receive):
        standard = self._perform_checkout(delivery_type="standard")
        express = self._perform_checkout(delivery_type="express")
        rule = DeliveryPricingRule.get_or_create_default()
        self.assertEqual(
            Decimal(express.data["total_amount"]) - Decimal(standard.data["total_amount"]),
            rule.express_surcharge,
        )

    def test_checkout_rejects_inactive_product(self, _can_receive):
        draft = ProductVariant.objects.filter(product__store=self.store_a).first()
        draft.product.status = Product.Status.DRAFT
        draft.product.save(update_fields=["status"])
        payload = self._checkout_payload([str(draft.id)])
        self.client.force_authenticate(self.customer)
        response = self.client.post("/api/orders/checkout/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_checkout_rejects_inactive_store(self, _can_receive):
        self.store_b.status = Store.Status.INACTIVE
        self.store_b.save(update_fields=["status"])
        payload = self._checkout_payload()
        self.client.force_authenticate(self.customer)
        response = self.client.post("/api/orders/checkout/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@patch("apps.commissions.services.can_receive_orders", return_value=True)
class MultiStoreIsolationTests(MultiStoreTestMixin, TestCase):
    def _checkout(self, *_args):
        response = self._perform_checkout()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return GlobalOrder.objects.get(pk=response.data["id"])

    def test_merchant_sees_only_own_suborders(self, _can_receive):
        global_order = self._checkout()
        order_b = global_order.orders.get(store_id=self.store_b.id)

        self.client.force_authenticate(self.merchant_a)
        list_a = self.client.get("/api/orders/")
        ids_a = [o["id"] for o in list_a.json()["results"]]
        self.assertNotIn(str(order_b.id), ids_a)
        detail = self.client.get(f"/api/orders/{order_b.id}/")
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_merchant_global_orders_include_only_their_store(self, *_args):
        def _go(store, amount):
            go = GlobalOrder.objects.create(customer=self.customer, address=self.address,
                                            total_amount=amount)
            Order.objects.create(customer=self.customer, store=store, address=self.address,
                                 global_order=go, total_amount=amount)
            return go

        go_a = _go(self.store_a, Decimal("2000"))
        go_b = _go(self.store_b, Decimal("1500"))

        self.client.force_authenticate(self.merchant_a)
        ids = [r["id"] for r in self.client.get("/api/orders/global-orders/").json()["results"]]
        self.assertIn(str(go_a.id), ids)
        self.assertNotIn(str(go_b.id), ids)

        self.client.force_authenticate(self.merchant_b)
        ids = [r["id"] for r in self.client.get("/api/orders/global-orders/").json()["results"]]
        self.assertIn(str(go_b.id), ids)
        self.assertNotIn(str(go_a.id), ids)


@patch("apps.commissions.services.can_receive_orders", return_value=True)
class MultiStoreCollectionTests(MultiStoreTestMixin, TestCase):
    def _ready_delivery(self, *_args):
        response = self._perform_checkout()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        global_order = GlobalOrder.objects.get(pk=response.data["id"])
        delivery = global_order.deliveries.first()
        delivery.assign_driver(self.driver)
        return delivery

    def test_out_of_order_collection_is_rejected(self, _can_receive):
        delivery = self._ready_delivery()
        self.client.force_authenticate(self.driver_user)
        second = delivery.pickups.order_by("-pickup_order").first()
        response = self.client.post(
            f"/api/orders/deliveries/{delivery.id}/collect-pickup/",
            {"pickup": str(second.id)}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_progressive_collection_flips_delivery_to_picked_up(self, _can_receive):
        delivery = self._ready_delivery()
        self.client.force_authenticate(self.driver_user)
        for pickup in delivery.pickups.order_by("pickup_order"):
            response = self.client.post(
                f"/api/orders/deliveries/{delivery.id}/collect-pickup/",
                {"pickup": str(pickup.id)}, format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            pickup.refresh_from_db()
            self.assertEqual(pickup.pickup_status, DeliveryPickup.Status.PICKED_UP)

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, Delivery.Status.PICKED_UP)
        done, total, all_done = delivery.pickups_status()
        self.assertEqual((done, total), (2, 2))
        self.assertTrue(all_done)

    def test_collect_by_unauthorized_user_is_forbidden(self, _can_receive):
        delivery = self._ready_delivery()
        self.client.force_authenticate(self.customer)
        pickup = delivery.pickups.first()
        response = self.client.post(
            f"/api/orders/deliveries/{delivery.id}/collect-pickup/",
            {"pickup": str(pickup.id)}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class GlobalPaymentTests(TestCase):
    """La confirmation du paiement global marque les sous-commandes payées une
    seule fois, avec une transaction unique (idempotence webhook)."""

    def setUp(self):
        Role.objects.get_or_create(name=Role.RoleName.MERCHANT)
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com",
                                         password="testpass123", is_verified=True)
        role = Role.objects.get(name=Role.RoleName.MERCHANT)
        UserRole.objects.create(user=owner, role=role)
        self.customer = self._client_user()
        self.store = Store.objects.create(owner=owner, name="Boutique", status=Store.Status.ACTIVE)
        self.address = Address.objects.create(user=self.customer, label="Domicile", city="Dakar")

    def _client_user(self):
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        role = Role.objects.get(name=Role.RoleName.CLIENT)
        user = User.objects.create_user(username="client@example.com", email="client@example.com",
                                        password="testpass123", is_verified=True)
        UserRole.objects.create(user=user, role=role)
        return user

    def _make_suborder(self, amount):
        order = Order.objects.create(
            customer=self.customer, store=self.store, address=self.address, total_amount=amount,
        )
        variant = ProductVariant.objects.create(
            product=Product.objects.create(store=self.store, name="P", base_price=amount,
                                           status=Product.Status.ACTIVE),
            sku=f"SKU-{abs(hash(amount))}", price=amount,
        )
        OrderItem.objects.create(order=order, product_variant=variant, quantity=1, unit_price=amount)
        return order

    def test_mark_succeeded_marks_suborders_and_is_idempotent(self):
        global_order = GlobalOrder.objects.create(customer=self.customer, address=self.address,
                                                  total_amount=Decimal("3500"))
        sub_a = self._make_suborder(Decimal("2000"))
        sub_b = self._make_suborder(Decimal("1500"))
        sub_a.global_order = global_order
        sub_a.save(update_fields=["global_order"])
        sub_b.global_order = global_order
        sub_b.save(update_fields=["global_order"])
        payment = Payment.objects.create(global_order=global_order, amount=Decimal("3500"), method="wave")

        payment.mark_succeeded()
        payment.mark_succeeded()  # webhook rejoué

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        for order in (sub_a, sub_b):
            order.refresh_from_db()
            self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(
            Transaction.objects.filter(payment=payment, type=Transaction.Type.SALE).count(),
            1,
        )

    def test_global_order_cancel_creates_refund_when_paid(self):
        from apps.payments.models import Refund

        global_order = GlobalOrder.objects.create(customer=self.customer, address=self.address,
                                                  total_amount=Decimal("1000"))
        sub = self._make_suborder(Decimal("1000"))
        sub.global_order = global_order
        sub.save(update_fields=["global_order"])
        delivery = Delivery.objects.create(global_order=global_order)
        payment = Payment.objects.create(global_order=global_order, amount=Decimal("1000"), method="wave")
        payment.mark_succeeded()

        client = APIClient()
        client.force_authenticate(self.customer)
        response = client.post(f"/api/orders/global-orders/{global_order.id}/cancel/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        global_order.refresh_from_db()
        sub.refresh_from_db()
        delivery.refresh_from_db()
        self.assertEqual(global_order.status, GlobalOrder.Status.CANCELLED)
        self.assertEqual(sub.status, Order.Status.CANCELLED)
        self.assertEqual(delivery.status, Delivery.Status.CANCELLED)
        self.assertTrue(Refund.objects.filter(payment=payment).exists())