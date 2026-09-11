"""
Tests pour le cycle de vie livreur/livraison : affectation, transitions de
statut, répercussion sur le statut de la commande, et diffusion temps réel
(GPS, événements SSE).
"""
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from apps.users.models import User, Role, UserRole
from apps.catalog.models import Store
from apps.orders.geoutils import compute_eta_seconds, point_in_polygon
from apps.orders.models import (
    Address, Delivery, DeliveryEvent, DeliveryPartner, DeliveryTracking,
    DeliveryZone, Driver, GlobalOrder, Order, PartnerInvoice, PartnerZonePricing,
)
from apps.orders.pricing import best_delivery_partner, compute_delivery_fee


class DeliveryLifecycleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        for role_name in (Role.RoleName.MERCHANT, Role.RoleName.DRIVER, Role.RoleName.CLIENT):
            Role.objects.get_or_create(name=role_name)

        self.merchant = self._make_user("merchant@example.com", Role.RoleName.MERCHANT)
        self.other_merchant = self._make_user("other-merchant@example.com", Role.RoleName.MERCHANT)
        self.driver_user = self._make_user("driver@example.com", Role.RoleName.DRIVER)
        self.customer = self._make_user("client@example.com", Role.RoleName.CLIENT)

        self.store = Store.objects.create(
            owner=self.merchant, name="Boutique",
            latitude=Decimal("14.716677"), longitude=Decimal("-17.467686"),
        )
        self.driver = Driver.objects.create(
            user=self.driver_user, availability_status=Driver.AvailabilityStatus.AVAILABLE,
            last_latitude=Decimal("14.716677"), last_longitude=Decimal("-17.467686"),
            position_updated_at=timezone.now(),
        )
        self.order = Order.objects.create(customer=self.customer, store=self.store, total_amount=5000)
        self.delivery = Delivery.objects.create(order=self.order)

    def _make_user(self, email, role_name):
        user = User.objects.create_user(username=email, email=email, password="testpass123", is_verified=True)
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def test_owner_merchant_can_assign_driver(self):
        self.client.force_authenticate(self.merchant)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/assign/", {"driver": str(self.driver.id)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.driver_id, self.driver.id)
        self.assertEqual(self.delivery.status, Delivery.Status.ASSIGNED)

    def test_other_merchant_cannot_assign_driver(self):
        self.client.force_authenticate(self.other_merchant)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/assign/", {"driver": str(self.driver.id)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_full_status_transition_updates_order(self):
        self.delivery.assign_driver(self.driver)
        self.client.force_authenticate(self.driver_user)

        # Le livreur récupère le colis : un code OTP est généré et lui est remis.
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/status/", {"status": "picked_up"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "picked_up")
        self.assertIn("confirmation_code", response.data)
        code = response.data["confirmation_code"]

        # La confirmation finale est faite par le CLIENT avec le code OTP,
        # pas par le livreur (la transition picked_up -> delivered lui est refusée).
        client_response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/status/", {"status": "delivered"}, format="json")
        self.assertEqual(client_response.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.customer)
        confirm = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/confirm/", {"code": code}, format="json")
        self.assertEqual(confirm.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm.data["status"], "delivered")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)

    def test_invalid_status_transition_is_rejected(self):
        # La livraison est encore "pending" : passer directement à "delivered" est invalide.
        self.delivery.assign_driver(self.driver)
        self.client.force_authenticate(self.driver_user)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/status/", {"status": "delivered"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unassigned_driver_cannot_update_status(self):
        other_driver_user = self._make_user("driver2@example.com", Role.RoleName.DRIVER)
        Driver.objects.create(user=other_driver_user)
        self.delivery.assign_driver(self.driver)

        self.client.force_authenticate(other_driver_user)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/status/", {"status": "picked_up"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_driver_me_creates_profile_lazily(self):
        new_driver_user = self._make_user("newdriver@example.com", Role.RoleName.DRIVER)
        self.client.force_authenticate(new_driver_user)
        response = self.client.get("/api/orders/drivers/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Driver.objects.filter(user=new_driver_user).exists())


class DeliveryOtpConfirmationTests(TestCase):
    """Confirmation de livraison par code OTP : génération à la récupération
    du colis, vérification par le client, limites d'essais et expiration."""

    def setUp(self):
        self.client = APIClient()
        for role_name in (Role.RoleName.MERCHANT, Role.RoleName.DRIVER, Role.RoleName.CLIENT, Role.RoleName.ADMIN):
            Role.objects.get_or_create(name=role_name)

        self.merchant = self._make_user("merchant@example.com", Role.RoleName.MERCHANT)
        self.admin = self._make_user("admin@example.com", Role.RoleName.ADMIN)
        self.driver_user = self._make_user("driver@example.com", Role.RoleName.DRIVER)
        self.customer = self._make_user("client@example.com", Role.RoleName.CLIENT)
        self.stranger = self._make_user("stranger@example.com", Role.RoleName.CLIENT)

        self.store = Store.objects.create(owner=self.merchant, name="Boutique")
        self.driver = Driver.objects.create(user=self.driver_user, availability_status=Driver.AvailabilityStatus.AVAILABLE)
        self.order = Order.objects.create(customer=self.customer, store=self.store, total_amount=5000)
        self.delivery = Delivery.objects.create(order=self.order)

    def _make_user(self, email, role_name):
        user = User.objects.create_user(username=email, email=email, password="testpass123", is_verified=True)
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def _pickup(self, return_code=True):
        """Fait récupérer le colis par le livreur ; renvoie la réponse si
        `return_code`, sinon le code OTP en clair."""
        self.delivery.assign_driver(self.driver)
        self.client.force_authenticate(self.driver_user)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/status/", {"status": "picked_up"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if return_code:
            return response
        return response.data["confirmation_code"]

    def test_pickup_generates_otp_and_returns_plaintext_once(self):
        response = self._pickup()
        self.assertRegex(response.data["confirmation_code"], r"^\d{6}$")
        self.delivery.refresh_from_db()
        # Stocké hashé uniquement : jamais lisible via le serializer classique.
        self.assertNotEqual(self.delivery.confirmation_otp_hash, response.data["confirmation_code"])
        self.assertIsNotNone(self.delivery.confirmation_otp_expires_at)

    def test_plaintext_otp_not_replayed_by_delivery_serializer(self):
        self._pickup()
        self.client.force_authenticate(self.driver_user)
        response = self.client.get(f"/api/orders/deliveries/{self.delivery.id}/")
        self.assertNotIn("confirmation_code", response.data)

    def test_customer_confirms_delivery_with_otp(self):
        code = self._pickup(return_code=False)
        self.client.force_authenticate(self.customer)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/confirm/", {"code": code}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "delivered")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
        # Le hash a été purgé après confirmation.
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.confirmation_otp_hash, "")

    def test_wrong_code_is_rejected_and_counts_attempt(self):
        code = self._pickup(return_code=False)
        self.client.force_authenticate(self.customer)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/confirm/", {"code": "000000"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.confirmation_attempts, 1)
        # Le vrai code reste valide après un échec.
        ok = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/confirm/", {"code": code}, format="json")
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

    def test_stranger_cannot_confirm(self):
        code = self._pickup(return_code=False)
        self.client.force_authenticate(self.stranger)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/confirm/", {"code": code}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_confirm_requires_picked_up_status(self):
        self.delivery.assign_driver(self.driver)
        self.client.force_authenticate(self.customer)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/confirm/", {"code": "123456"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(MAX_OTP_ATTEMPTS=2)
    def test_attempts_exhausted_invalidates_code(self):
        code = self._pickup(return_code=False)
        self.client.force_authenticate(self.customer)
        url = f"/api/orders/deliveries/{self.delivery.id}/confirm/"
        self.assertEqual(self.client.post(url, {"code": "000000"}, format="json").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.post(url, {"code": "000001"}, format="json").status_code, status.HTTP_400_BAD_REQUEST)
        # Même le bon code n'est plus accepté : il faut en régénérer un.
        response = self.client.post(url, {"code": code}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Trop d'essais", str(response.data))

    def test_expired_code_is_rejected(self):
        code = self._pickup(return_code=False)
        self.delivery.confirmation_otp_expires_at = timezone.now() - timedelta(minutes=1)
        self.delivery.save(update_fields=["confirmation_otp_expires_at"])
        self.client.force_authenticate(self.customer)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/confirm/", {"code": code}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_driver_cannot_mark_delivered_directly(self):
        self._pickup()
        self.client.force_authenticate(self.driver_user)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/status/", {"status": "delivered"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Le statut reste picked_up (le code saisi n'est pas utilisé ici).
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.Status.PICKED_UP)

    def test_driver_regenerates_otp_invalidating_previous(self):
        old_code = self._pickup(return_code=False)
        self.client.force_authenticate(self.driver_user)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/regenerate-otp/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_code = response.data["confirmation_code"]
        self.assertRegex(new_code, r"^\d{6}$")
        self.assertNotEqual(new_code, old_code)
        self.client.force_authenticate(self.customer)
        self.assertEqual(
            self.client.post(f"/api/orders/deliveries/{self.delivery.id}/confirm/", {"code": old_code}, format="json").status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        ok = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/confirm/", {"code": new_code}, format="json")
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

    def test_admin_can_bypass_otp_via_status(self):
        self._pickup()
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/status/", {"status": "delivered"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "delivered")

    def test_unknown_regeneration_returns_400_outside_picked_up(self):
        self.delivery.assign_driver(self.driver)
        self.client.force_authenticate(self.driver_user)
        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/regenerate-otp/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DeliveryTrackingTests(TestCase):
    """Suivi GPS : partage de position, broadcast temps réel et ETA."""

    def setUp(self):
        self.client = APIClient()
        for role_name in (Role.RoleName.MERCHANT, Role.RoleName.DRIVER, Role.RoleName.CLIENT):
            Role.objects.get_or_create(name=role_name)

        self.merchant = self._make_user("merchant@example.com", Role.RoleName.MERCHANT)
        self.driver_user = self._make_user("driver@example.com", Role.RoleName.DRIVER)
        self.customer = self._make_user("client@example.com", Role.RoleName.CLIENT)

        self.store = Store.objects.create(owner=self.merchant, name="Boutique")
        self.driver = Driver.objects.create(user=self.driver_user, availability_status=Driver.AvailabilityStatus.AVAILABLE)
        self.order = Order.objects.create(customer=self.customer, store=self.store, total_amount=5000)
        self.delivery = Delivery.objects.create(order=self.order)

    def _make_user(self, email, role_name):
        user = User.objects.create_user(username=email, email=email, password="testpass123", is_verified=True)
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def test_assigned_driver_shares_position_and_publishes_event(self):
        self.delivery.assign_driver(self.driver)
        self.client.force_authenticate(self.driver_user)
        with patch("apps.orders.realtime.publish_delivery_event") as publish:
            response = self.client.post(
                f"/api/orders/deliveries/{self.delivery.id}/track/",
                {"latitude": "14.716677", "longitude": "-17.467686"},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        publish.assert_called_once()
        delivery_id, event_type, payload = publish.call_args.args
        self.assertEqual(delivery_id, self.delivery.id)
        self.assertEqual(event_type, "position")
        self.assertEqual(payload["last_position"]["latitude"], "14.716677")
        self.assertEqual(payload["last_position"]["longitude"], "-17.467686")
        self.assertEqual(payload["status"], "assigned")
        # L'instance est bien persistée et désignée comme dernière position.
        self.assertEqual(
            self.delivery.trackings.first(),
            DeliveryTracking.objects.get(delivery=self.delivery),
        )

    def test_unassigned_driver_cannot_share_position(self):
        other_driver_user = self._make_user("driver2@example.com", Role.RoleName.DRIVER)
        Driver.objects.create(user=other_driver_user)
        self.delivery.assign_driver(self.driver)
        self.client.force_authenticate(other_driver_user)
        response = self.client.post(
            f"/api/orders/deliveries/{self.delivery.id}/track/",
            {"latitude": "14.71", "longitude": "-17.46"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_driver_current_position_returns_latest(self):
        self.delivery.assign_driver(self.driver)
        DeliveryTracking.objects.create(delivery=self.delivery, latitude="14.71", longitude="-17.46")
        DeliveryTracking.objects.create(delivery=self.delivery, latitude="14.79", longitude="-17.52")
        position = self.driver.current_position()
        self.assertEqual(position["latitude"], Decimal("14.79"))
        self.assertEqual(position["longitude"], Decimal("-17.52"))

    def test_update_status_publishes_realtime_event(self):
        self.delivery.assign_driver(self.driver)
        self.client.force_authenticate(self.driver_user)
        with patch("apps.orders.realtime.publish_delivery_event") as publish:
            response = self.client.post(
                f"/api/orders/deliveries/{self.delivery.id}/status/",
                {"status": "picked_up"},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        publish.assert_called_once()
        delivery_id, event_type, payload = publish.call_args.args
        self.assertEqual(event_type, "status")
        self.assertEqual(payload["status"], "picked_up")
        self.assertIn("récupéré", payload["message"])

    def test_delivery_serializer_exposes_eta_and_last_position(self):
        address = Address.objects.create(user=self.customer, label="Accueil", latitude="14.71", longitude="-17.46")
        self.order.address = address
        self.order.save(update_fields=["address"])
        self.delivery.assign_driver(self.driver)
        DeliveryTracking.objects.create(delivery=self.delivery, latitude="14.716677", longitude="-17.467686")
        self.client.force_authenticate(self.merchant)
        response = self.client.get(f"/api/orders/deliveries/{self.delivery.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("eta_seconds", response.data)
        self.assertEqual(response.data["last_position"]["latitude"], Decimal("14.716677"))


class DeliveryEventsStreamTests(TestCase):
    """Endpoint SSE : instantané à la connexion + confinement par sécurité."""

    def setUp(self):
        self.client = APIClient()
        for role_name in (Role.RoleName.MERCHANT, Role.RoleName.DRIVER, Role.RoleName.CLIENT, Role.RoleName.ADMIN):
            Role.objects.get_or_create(name=role_name)

        self.merchant = self._make_user("merchant@example.com", Role.RoleName.MERCHANT)
        self.driver_user = self._make_user("driver@example.com", Role.RoleName.DRIVER)
        self.customer = self._make_user("client@example.com", Role.RoleName.CLIENT)

        self.store = Store.objects.create(
            owner=self.merchant, name="Boutique",
            latitude=Decimal("14.716677"), longitude=Decimal("-17.467686"),
        )
        self.driver = Driver.objects.create(
            user=self.driver_user, availability_status=Driver.AvailabilityStatus.AVAILABLE,
            last_latitude=Decimal("14.716677"), last_longitude=Decimal("-17.467686"),
            position_updated_at=timezone.now(),
        )
        self.order = Order.objects.create(customer=self.customer, store=self.store, total_amount=5000)
        self.delivery = Delivery.objects.create(order=self.order)

    def _make_user(self, email, role_name):
        user = User.objects.create_user(username=email, email=email, password="testpass123", is_verified=True)
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def test_customer_receives_snapshot_on_events_stream(self):
        self.client.force_authenticate(self.customer)
        response = self.client.get(f"/api/orders/deliveries/{self.delivery.id}/events/")
        # Lecture d'un seul chunk : le flux SSE est infini, on ne le matérialise pas.
        chunk = next(response.streaming_content).decode("utf-8")
        self.assertIn("data:", chunk)
        self.assertIn('"event": "snapshot"', chunk)
        self.assertIn('"status": "pending"', chunk)
        self.assertIn('"eta_seconds"', chunk)

    def test_events_stream_forbidden_for_stranger(self):
        stranger = self._make_user("stranger@example.com", Role.RoleName.CLIENT)
        self.client.force_authenticate(stranger)
        response = self.client.get(f"/api/orders/deliveries/{self.delivery.id}/events/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_events_stream_requires_authentication(self):
        response = self.client.get(f"/api/orders/deliveries/{self.delivery.id}/events/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class DeliveryGeoUtilsTests(TestCase):
    """Logique géographique pure : polygones et ETA."""

    def test_point_in_polygon(self):
        polygon = [[14.71, -17.46], [14.72, -17.46], [14.72, -17.47], [14.71, -17.47]]
        self.assertTrue(point_in_polygon(14.715, -17.465, polygon))
        self.assertFalse(point_in_polygon(16.0, -20.0, polygon))

    def test_zone_contains_uses_boundary(self):
        zone = DeliveryZone.objects.create(
            name="Dakar",
            boundary_geojson={
                "type": "Polygon",
                "coordinates": [[[-17.46, 14.71], [-17.46, 14.72], [-17.47, 14.72], [-17.47, 14.71], [-17.46, 14.71]]],
            },
        )
        self.assertTrue(zone.contains(14.715, -17.465))
        self.assertFalse(zone.contains(16.0, -20.0))
        # Zone sans frontière → on refuse (aucune assertion fausse de couverture totale).
        empty_zone = DeliveryZone.objects.create(name="Sans limite")
        self.assertFalse(empty_zone.contains(14.7, -17.4))

    def test_compute_eta_returns_none_without_coordinates(self):
        self.assertIsNone(compute_eta_seconds(None, -17.46, 14.71, -17.46))
        self.assertIsNone(compute_eta_seconds("abc", -17.46, 14.71, -17.46))

    def test_compute_eta_positive_for_distant_points(self):
        seconds = compute_eta_seconds(14.7, -17.4, 14.9, -16.5)
        self.assertIsInstance(seconds, int)
        self.assertGreater(seconds, 0)


class DriverWorkflowTests(TestCase):
    """Gestion des livreurs par l'admin + affectation à proximité de la boutique."""

    def setUp(self):
        self.client = APIClient()
        for role_name in (Role.RoleName.MERCHANT, Role.RoleName.DRIVER, Role.RoleName.CLIENT, Role.RoleName.ADMIN):
            Role.objects.get_or_create(name=role_name)

        self.admin = self._make_user("admin@example.com", Role.RoleName.ADMIN)
        self.merchant = self._make_user("merchant@example.com", Role.RoleName.MERCHANT)
        self.driver_user = self._make_user("driver@example.com", Role.RoleName.DRIVER)
        self.customer = self._make_user("client@example.com", Role.RoleName.CLIENT)

        self.store = Store.objects.create(
            owner=self.merchant, name="Boutique",
            latitude=Decimal("14.716677"), longitude=Decimal("-17.467686"),
        )
        self.driver = Driver.objects.create(
            user=self.driver_user, availability_status=Driver.AvailabilityStatus.AVAILABLE,
            last_latitude=Decimal("14.716677"), last_longitude=Decimal("-17.467686"),
            position_updated_at=timezone.now(),
        )
        self.order = Order.objects.create(customer=self.customer, store=self.store, total_amount=5000)
        self.delivery = Delivery.objects.create(order=self.order)

    def _make_user(self, email, role_name):
        user = User.objects.create_user(username=email, email=email, password="testpass123", is_verified=True)
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def test_admin_creates_driver_account(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/orders/drivers/register/",
            {
                "email": "new-driver@example.com",
                "first_name": "Awa",
                "last_name": "Diop",
                "phone": "+221770000000",
                "vehicle_type": "moto",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIn("temporary_password", response.data)
        user = User.objects.get(email="new-driver@example.com")
        self.assertTrue(user.check_password(response.data["temporary_password"]))
        self.assertTrue(user.is_verified)
        self.assertTrue(user.must_change_password)
        self.assertTrue(user.has_role(Role.RoleName.DRIVER))
        driver = Driver.objects.get(user=user)
        self.assertEqual(driver.availability_status, Driver.AvailabilityStatus.OFFLINE)
        # Le mot de passe provisoire ne doit pas être stocké dans la réponse.
        driver_user = User.objects.get(email="new-driver@example.com")
        self.assertNotEqual(driver_user.password, response.data["temporary_password"])

    def test_only_admin_can_register_driver(self):
        self.client.force_authenticate(self.merchant)
        response = self.client.post(
            "/api/orders/drivers/register/",
            {"email": "x@example.com", "first_name": "X", "last_name": "Y", "vehicle_type": "moto"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_register_driver_rejects_duplicate_email(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/orders/drivers/register/",
            {"email": self.driver_user.email, "first_name": "Z", "last_name": "Z", "vehicle_type": "moto"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_driver_defaults_to_offline_until_available(self):
        self.client.force_authenticate(self.merchant)
        # Un livreur offline (vient d'être créé par l'admin) ne doit pas apparaître.
        new_user = get_user_model().objects.create_user(
            username="off@example.com", email="off@example.com", password="testpass123",
            is_verified=True, must_change_password=True,
        )
        UserRole.objects.create(user=new_user, role=Role.objects.get(name=Role.RoleName.DRIVER))
        Driver.objects.create(
            user=new_user, availability_status=Driver.AvailabilityStatus.OFFLINE,
            last_latitude=self.driver.last_latitude, last_longitude=self.driver.last_longitude,
        )
        response = self.client.get("/api/orders/drivers/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        driver_ids = [d["id"] for d in response.data["results"]]
        self.assertIn(str(self.driver.id), driver_ids)
        self.assertNotIn(str(Driver.objects.get(user=new_user).id), driver_ids)

    def test_assign_requires_driver_free_position_near_store(self):
        self.client.force_authenticate(self.merchant)
        # Livreur SANS position libre : affectation refusée.
        far_user = self._make_user("far@example.com", Role.RoleName.DRIVER)
        far_driver = Driver.objects.create(user=far_user, availability_status=Driver.AvailabilityStatus.AVAILABLE)
        response = self.client.post(
            f"/api/orders/deliveries/{self.delivery.id}/assign/", {"driver": str(far_driver.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.delivery.refresh_from_db()
        self.assertIsNone(self.delivery.driver)

    def test_assign_rejects_driver_far_from_store(self):
        self.client.force_authenticate(self.merchant)
        far_user = self._make_user("far2@example.com", Role.RoleName.DRIVER)
        far_driver = Driver.objects.create(
            user=far_user, availability_status=Driver.AvailabilityStatus.AVAILABLE,
            last_latitude=Decimal("16.000000"), last_longitude=Decimal("-16.000000"),
            position_updated_at=timezone.now(),
        )
        response = self.client.post(
            f"/api/orders/deliveries/{self.delivery.id}/assign/", {"driver": str(far_driver.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_text = str(response.data)
        self.assertIn("km", error_text)

    def test_assign_accepts_driver_near_store(self):
        self.client.force_authenticate(self.merchant)
        response = self.client.post(
            f"/api/orders/deliveries/{self.delivery.id}/assign/", {"driver": str(self.driver.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.driver_id, self.driver.id)

    def test_list_drivers_near_store_with_distance(self):
        self.client.force_authenticate(self.merchant)
        response = self.client.get(f"/api/orders/drivers/?store={self.store.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], str(self.driver.id))
        self.assertAlmostEqual(response.data[0]["distance_km"], 0.0, places=1)

    def test_driver_share_position_endpoint(self):
        self.client.force_authenticate(self.driver_user)
        response = self.client.post(
            "/api/orders/drivers/me/position/",
            {"latitude": "14.720000", "longitude": "-17.470000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.last_latitude, Decimal("14.720000"))
        self.assertIsNotNone(self.driver.position_updated_at)

    def test_non_driver_cannot_share_position(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post("/api/orders/drivers/me/position/", {"latitude": "1", "longitude": "2"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


def _dakar_zone():
    return DeliveryZone.objects.create(
        name="Dakar",
        boundary_geojson={
            "type": "Polygon",
            "coordinates": [[[-17.46, 14.71], [-17.46, 14.72], [-17.47, 14.72], [-17.47, 14.71], [-17.46, 14.71]]],
        },
    )


class PartnerSelectionTests(TestCase):
    """Sélection du meilleur partenaire par zone + tarifs de la grille zone."""

    def setUp(self):
        for role_name in (
            Role.RoleName.PARTNER, Role.RoleName.MERCHANT, Role.RoleName.DRIVER, Role.RoleName.CLIENT,
        ):
            Role.objects.get_or_create(name=role_name)
        self.zone = _dakar_zone()
        self.merchant = User.objects.create_user(
            username="m@example.com", email="m@example.com", password="x", is_verified=True
        )
        UserRole.objects.create(user=self.merchant, role=Role.objects.get(name=Role.RoleName.MERCHANT))
        self.store = Store.objects.create(
            owner=self.merchant, name="Boutique",
            latitude=Decimal("14.716677"), longitude=Decimal("-17.467686"),
        )
        self.customer = User.objects.create_user(
            username="c@example.com", email="c@example.com", password="x", is_verified=True
        )
        UserRole.objects.create(user=self.customer, role=Role.objects.get(name=Role.RoleName.CLIENT))
        self.address = Address.objects.create(
            user=self.customer, label="Maison", latitude=Decimal("14.715000"), longitude=Decimal("-17.465000"),
        )

    def _partner(self, name, score=60.0, active=True, fee=Decimal("1200"), cost=Decimal("800")):
        partner = DeliveryPartner.objects.create(
            name=name, contact_name=name, contact_email=f"{name}@ex.com", contact_phone="+22177",
            status=DeliveryPartner.Status.ACTIVE if active else DeliveryPartner.Status.INACTIVE,
            score=Decimal(str(score)),
        )
        PartnerZonePricing.objects.create(
            partner=partner, zone=self.zone,
            client_fee=fee, partner_cost=cost,
            estimated_delay_minutes=40, max_weight_kg=10, is_available=True,
        )
        return partner

    def test_best_partner_picks_highest_score_active_company(self):
        self._partner("B", score=70.0, fee=Decimal("1500"))
        self._partner("Best", score=98.0, fee=Decimal("1300"))
        self._partner("Inactif", score=99.0, active=False)
        best = best_delivery_partner(self.address)
        self.assertIsNotNone(best)
        self.assertEqual(best.name, "Best")

    def test_best_partner_returns_none_without_zone_coverage(self):
        partner = self._partner("B", fee=Decimal("1500"))
        PartnerZonePricing.objects.filter(partner=partner).update(is_available=False)
        self.assertIsNone(best_delivery_partner(self.address))

    def test_compute_delivery_fee_uses_partner_client_fee(self):
        partner = self._partner("CityCourier", fee=Decimal("1200"), cost=Decimal("800"))
        fee = compute_delivery_fee(self.store, self.address, "standard", partner=partner)
        self.assertEqual(fee, Decimal("1200"))

    def test_compute_delivery_fee_express_adds_surcharge(self):
        partner = self._partner("CityCourier", fee=Decimal("1200"), cost=Decimal("800"))
        fee = compute_delivery_fee(self.store, self.address, "express", partner=partner)
        self.assertEqual(fee, Decimal("2000"))

    def test_partner_cost_for_delivery_uses_zone_cost(self):
        partner = self._partner("CityCourier", fee=Decimal("1200"), cost=Decimal("800"))
        order = Order.objects.create(customer=self.customer, store=self.store, address=self.address, total_amount=2000)
        delivery = Delivery.objects.create(order=order)
        self.assertEqual(partner.partner_cost_for(delivery), Decimal("800"))

    def test_assign_partner_marks_delivery_and_traces_event(self):
        partner = self._partner("CityCourier")
        order = Order.objects.create(customer=self.customer, store=self.store, address=self.address, total_amount=2000)
        delivery = Delivery.objects.create(order=order)
        delivery.assign_partner(partner)
        delivery.refresh_from_db()
        self.assertEqual(delivery.partner_id, partner.id)
        self.assertEqual(delivery.status, Delivery.Status.ASSIGNED)
        self.assertIsNotNone(delivery.assigned_at)
        self.assertRegex(delivery.reference, r"^DLV-\d{8}-\d{6}$")
        self.assertEqual(delivery.events.filter(action="pending→assigned").count(), 1)

    def test_invoice_next_reference_and_balance(self):
        partner = self._partner("CityCourier")
        invoice = PartnerInvoice.objects.create(
            partner=partner, period_start=timezone.localdate().replace(day=1),
            period_end=timezone.localdate(),
            total_due=Decimal("10000"), collection_fees=Decimal("1000"),
            marketplace_deliveries_count=5, on_demand_deliveries_count=2,
        )
        self.assertRegex(invoice.reference, r"^INV-\d{6}-\d{5}$")
        self.assertEqual(invoice.balance, Decimal("9000"))


class PartnerStatusFlowTests(TestCase):
    """Nouvelle chaîne de statuts à la spec §5, en model-level."""

    def setUp(self):
        for role_name in (Role.RoleName.MERCHANT, Role.RoleName.DRIVER, Role.RoleName.CLIENT):
            Role.objects.get_or_create(name=role_name)
        self.merchant = User.objects.create_user(
            username="m@example.com", email="m@example.com", password="x", is_verified=True
        )
        UserRole.objects.create(user=self.merchant, role=Role.objects.get(name=Role.RoleName.MERCHANT))
        self.driver_user = User.objects.create_user(
            username="d@example.com", email="d@example.com", password="x", is_verified=True
        )
        UserRole.objects.create(user=self.driver_user, role=Role.objects.get(name=Role.RoleName.DRIVER))
        self.customer = User.objects.create_user(
            username="c@example.com", email="c@example.com", password="x", is_verified=True
        )
        UserRole.objects.create(user=self.customer, role=Role.objects.get(name=Role.RoleName.CLIENT))
        self.store = Store.objects.create(
            owner=self.merchant, name="Boutique",
            latitude=Decimal("14.716677"), longitude=Decimal("-17.467686"),
        )
        self.driver = Driver.objects.create(
            user=self.driver_user, availability_status=Driver.AvailabilityStatus.AVAILABLE,
            last_latitude=Decimal("14.716677"), last_longitude=Decimal("-17.467686"),
            position_updated_at=timezone.now(),
        )
        self.order = Order.objects.create(customer=self.customer, store=self.store, total_amount=5000)
        self.delivery = Delivery.objects.create(order=self.order)
        self.delivery.assign_driver(self.driver)

    def test_accept_then_defines_transition_chain(self):
        self.delivery.accept(user=self.driver_user)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.Status.ACCEPTED)
        self.assertIsNotNone(self.delivery.accepted_at)
        # pickup via le flux status update simulé
        self.delivery.status = Delivery.Status.PICKUP_PENDING
        self.delivery.save()
        self.delivery._transition_to(Delivery.Status.PICKED_UP)
        self.delivery.refresh_from_db()
        for s in (Delivery.Status.IN_TRANSIT, Delivery.Status.OUT_FOR_DELIVERY):
            self.delivery._transition_to(s)
        self.assertIsNotNone(self.delivery.in_transit_at)
        self.assertIsNotNone(self.delivery.out_for_delivery_at)
        self.assertEqual(self.delivery.events.filter(action="status_changed").count(), 4)

    def test_accept_forbidden_for_unassigned_driver(self):
        other = User.objects.create_user(username="other@example.com", email="other@example.com", password="x")
        UserRole.objects.create(user=other, role=Role.objects.get(name=Role.RoleName.DRIVER))
        with self.assertRaises(PermissionError):
            self.delivery.accept(user=other)

    def test_refuse_clears_driver_and_records_reason(self):
        self.delivery.refuse(user=self.driver_user, reason=Delivery.FailureReason.TRANSPORT_ISSUE, comment="Panne")
        self.delivery.refresh_from_db()
        self.assertIsNone(self.delivery.driver_id)
        self.assertEqual(self.delivery.refuse_reason, Delivery.FailureReason.TRANSPORT_ISSUE)
        self.assertIn("Panne", self.delivery.failure_comment)
        self.assertEqual(self.delivery.events.filter(action="refused").count(), 1)

    def test_fail_requires_reason_and_sets_failure_fields(self):
        with self.assertRaises(ValueError):
            self.delivery.mark_failed(user=self.driver_user, reason=None)
        self.delivery.mark_failed(
            user=self.driver_user, reason=Delivery.FailureReason.NUMBER_UNREACHABLE, comment="Rappel impossible"
        )
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.Status.DELIVERY_FAILED)
        self.assertEqual(self.delivery.failure_reason, Delivery.FailureReason.NUMBER_UNREACHABLE)
        self.assertIsNotNone(self.delivery.failed_at)

    def test_return_flow_from_out_for_delivery(self):
        self.delivery._transition_to(Delivery.Status.OUT_FOR_DELIVERY)
        self.delivery.request_return(
            user=self.driver_user, reason=Delivery.ReturnReason.CUSTOMER_ABSENT, comment="Personne à domicile"
        )
        self.delivery.mark_returned(user=self.driver_user, comment="Rendu au vendeur")
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.Status.RETURNED)
        self.assertIsNotNone(self.delivery.returned_at)

    def test_cancel_traces_event_from_assigned(self):
        self.delivery.cancel(user=None, comment="Annulation test")
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.Status.CANCELLED)
        self.assertIsNotNone(self.delivery.cancelled_at)


class PartnerSpaceApiTests(TestCase):
    """Espace Partenaire : scoping, création de livreur, stats."""

    def setUp(self):
        self.client = APIClient()
        for role_name in (
            Role.RoleName.PARTNER, Role.RoleName.MERCHANT, Role.RoleName.DRIVER, Role.RoleName.CLIENT,
        ):
            Role.objects.get_or_create(name=role_name)
        self.zone = _dakar_zone()

        self.admin = User.objects.create_user(username="admin@example.com", email="admin@example.com", password="x")
        UserRole.objects.create(user=self.admin, role=Role.objects.get(name=Role.RoleName.ADMIN))

        self.partner_user = User.objects.create_user(
            username="p@example.com", email="p@example.com", password="x", is_verified=True
        )
        UserRole.objects.create(user=self.partner_user, role=Role.objects.get(name=Role.RoleName.PARTNER))
        self.partner = DeliveryPartner.objects.create(
            name="CityCourier", contact_name="Aliou", contact_email="p@example.com", contact_phone="+221770000001",
            status=DeliveryPartner.Status.ACTIVE, user=self.partner_user,
        )
        PartnerZonePricing.objects.create(
            partner=self.partner, zone=self.zone, client_fee=Decimal("1200"),
            partner_cost=Decimal("800"), estimated_delay_minutes=40, max_weight_kg=10, is_available=True,
        )

        self.other_partner = DeliveryPartner.objects.create(
            name="OtherExpress", contact_name="Autre", contact_email="other@ex.com", contact_phone="+221770000002",
            status=DeliveryPartner.Status.ACTIVE,
        )
        self.merchant = User.objects.create_user(username="m@example.com", email="m@example.com", password="x")
        UserRole.objects.create(user=self.merchant, role=Role.objects.get(name=Role.RoleName.MERCHANT))
        self.store = Store.objects.create(
            owner=self.merchant, name="Boutique",
            latitude=Decimal("14.716677"), longitude=Decimal("-17.467686"),
        )
        self.customer = User.objects.create_user(username="c@example.com", email="c@example.com", password="x")
        UserRole.objects.create(user=self.customer, role=Role.objects.get(name=Role.RoleName.CLIENT))
        self.driver_user = User.objects.create_user(username="d@example.com", email="d@example.com", password="x")
        UserRole.objects.create(user=self.driver_user, role=Role.objects.get(name=Role.RoleName.DRIVER))
        self.driver = Driver.objects.create(
            user=self.driver_user, availability_status=Driver.AvailabilityStatus.AVAILABLE,
            last_latitude=Decimal("14.716677"), last_longitude=Decimal("-17.467686"),
            position_updated_at=timezone.now(), partner=self.partner,
        )
        self.order = Order.objects.create(customer=self.customer, store=self.store, total_amount=5000)
        self.delivery = Delivery.objects.create(order=self.order, partner=self.partner)

    def _as(self, user):
        self.client.force_authenticate(user)

    def test_partner_profile_and_stats(self):
        self._as(self.partner_user)
        profile = self.client.get("/api/orders/partner/profile/")
        self.assertEqual(profile.status_code, status.HTTP_200_OK)
        self.assertEqual(profile.data["name"], "CityCourier")
        stats = self.client.get("/api/orders/partner/stats/")
        self.assertEqual(stats.status_code, status.HTTP_200_OK)
        self.assertEqual(stats.data["deliveries_total"], 1)
        self.assertEqual(stats.data["active_drivers"], 1)

    def test_partner_sees_only_own_deliveries(self):
        other_order = Order.objects.create(customer=self.customer, store=self.store, total_amount=3000)
        Delivery.objects.create(order=other_order, partner=self.other_partner)
        self._as(self.partner_user)
        response = self.client.get("/api/orders/deliveries/")
        ids = [d["id"] for d in response.data["results"]]
        self.assertIn(str(self.delivery.id), ids)
        self.assertNotIn(str(Delivery.objects.get(order=other_order).id), ids)

    def test_partner_cannot_assign_other_company_driver(self):
        other_driver_user = User.objects.create_user(username="d2@example.com", email="d2@example.com", password="x")
        UserRole.objects.create(user=other_driver_user, role=Role.objects.get(name=Role.RoleName.DRIVER))
        other_driver = Driver.objects.create(
            user=other_driver_user, availability_status=Driver.AvailabilityStatus.AVAILABLE,
            last_latitude=Decimal("14.716677"), last_longitude=Decimal("-17.467686"),
            position_updated_at=timezone.now(), partner=self.other_partner,
        )
        self._as(self.partner_user)
        response = self.client.post(
            f"/api/orders/deliveries/{self.delivery.id}/assign/", {"driver": str(other_driver.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partner_registers_its_own_driver(self):
        self._as(self.partner_user)
        response = self.client.post(
            "/api/orders/drivers/register/",
            {
                "email": "courier@citycourier.sn",
                "first_name": "Awa", "last_name": "Diop",
                "phone": "+221770000003", "vehicle_type": "moto",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        driver = Driver.objects.get(user__email="courier@citycourier.sn")
        self.assertEqual(driver.partner_id, self.partner.id)

    def test_partner_sees_only_its_own_drivers(self):
        self._as(self.partner_user)
        # un autre compte partenaire sans entreprise liée n'existe pas ici ;
        # on vérifie juste que le scoping des livreurs listés est strict.
        other_driver_user = User.objects.create_user(username="d3@example.com", email="d3@example.com", password="x")
        UserRole.objects.create(user=other_driver_user, role=Role.objects.get(name=Role.RoleName.DRIVER))
        Driver.objects.create(
            user=other_driver_user, availability_status=Driver.AvailabilityStatus.OFFLINE, partner=self.other_partner,
        )
        response = self.client.get("/api/orders/drivers/")
        driver_ids = [d["id"] for d in response.data["results"]]
        self.assertIn(str(self.driver.id), driver_ids)
        self.assertNotIn(str(Driver.objects.get(user=other_driver_user).id), driver_ids)

    def test_partner_delivery_suggest_and_timeline(self):
        self.delivery.assign_driver(self.driver, user=self.partner_user)
        self.delivery.accept(user=self.driver_user)
        self._as(self.partner_user)
        timeline = self.client.get(f"/api/orders/deliveries/{self.delivery.id}/events-history/")
        self.assertEqual(timeline.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(timeline.data), 2)
        detail = self.client.get(f"/api/orders/deliveries/{self.delivery.id}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["status"], Delivery.Status.ACCEPTED)

    def test_admin_manages_partners_and_rotates_key(self):
        self._as(self.admin)
        created = self.client.post(
            "/api/orders/partners/",
            {
                "name": "NewCo", "contact_name": "Ndiaye", "contact_email": "nc@ex.com",
                "contact_phone": "+221770000004",
            },
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        pk = created.data["id"]
        self._as(self.admin)
        key = self.client.post(f"/api/orders/partners/{pk}/rotate-api-key/", {}, format="json")
        self.assertEqual(key.status_code, status.HTTP_200_OK)
        self.assertIn("api_key", key.data)
        self.assertIn("api_key_last4", key.data)

    def test_partner_zone_pricing_readable(self):
        self._as(self.partner_user)
        response = self.client.get("/api/orders/partner/zones/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(float(response.data[0]["client_fee"]), 1200.0)


class TrackOrderGuestTests(TestCase):
    """Endpoint /api/orders/track/ — suivi de commande invité (sans connexion)."""

    def setUp(self):
        self.client = APIClient()
        Role.objects.get_or_create(name=Role.RoleName.MERCHANT)
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        self.merchant = User.objects.create_user(
            username="merchant-t@example.com", email="merchant-t@example.com",
            password="testpass123", is_verified=True,
        )
        UserRole.objects.create(
            user=self.merchant, role=Role.objects.get(name=Role.RoleName.MERCHANT)
        )
        self.store = Store.objects.create(owner=self.merchant, name="Boutique T")
        self.customer = User.objects.create_user(
            username="client-guest@example.com", email="client-guest@example.com",
            password="testpass123", is_verified=True,
        )
        self.order = Order.objects.create(
            customer=self.customer, store=self.store, total_amount=7500,
            status=Order.Status.PENDING,
        )

    def _unicode_order(self, reference="SM-TRACK-000001"):
        gorder = GlobalOrder.objects.create(
            reference=reference, customer=self.customer, items_total=5000,
            delivery_fee=1000, total_amount=6000, status=GlobalOrder.Status.PAID,
        )
        Order.objects.create(
            customer=self.customer, store=self.store, global_order=gorder,
            total_amount=5000, status=Order.Status.PAID,
        )
        return gorder

    def test_track_global_order_by_reference_and_email(self):
        """Sans authentification, retrouve une commande globale par référence+email."""
        gorder = self._unicode_order()
        response = self.client.post(
            "/api/orders/track/",
            {"reference": gorder.reference, "email": self.customer.email},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["reference"], gorder.reference)
        self.assertEqual(response.data["status"], GlobalOrder.Status.PAID)
        self.assertEqual(response.data["total_amount"], "6000.00")

    def test_track_single_order_by_uuid_and_email(self):
        """Une commande simple (UUID) est traçable sans connexion."""
        response = self.client.post(
            "/api/orders/track/",
            {"reference": str(self.order.id), "email": self.customer.email},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_amount"], "7500.00")
        self.assertEqual(response.data["store_name"], "Boutique T")

    def test_track_wrong_email_gives_404(self):
        gorder = self._unicode_order()
        response = self.client.post(
            "/api/orders/track/",
            {"reference": gorder.reference, "email": "someone-else@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_track_missing_fields_gives_400(self):
        response = self.client.post("/api/orders/track/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_track_requires_reference_match(self):
        self._unicode_order(reference="SM-TRACK-000002")
        response = self.client.post(
            "/api/orders/track/",
            {"reference": "SM-UNKNOWN-000999", "email": self.customer.email},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_track_ignores_invalid_uuid_reference(self):
        """Une référence qui n'est pas un UUID ne crée pas d'erreur serveur."""
        response = self.client.post(
            "/api/orders/track/",
            {"reference": "not-a-uuid", "email": self.customer.email},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
