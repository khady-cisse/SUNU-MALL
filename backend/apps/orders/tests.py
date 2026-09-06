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
from apps.orders.models import Address, Delivery, DeliveryTracking, DeliveryZone, Driver, Order


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
