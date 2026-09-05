"""
Tests pour le cycle de vie livreur/livraison : affectation, transitions de
statut, répercussion sur le statut de la commande, et diffusion temps réel
(GPS, événements SSE).
"""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
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

        self.store = Store.objects.create(owner=self.merchant, name="Boutique")
        self.driver = Driver.objects.create(user=self.driver_user, availability_status=Driver.AvailabilityStatus.AVAILABLE)
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

        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/status/", {"status": "picked_up"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "picked_up")

        response = self.client.post(f"/api/orders/deliveries/{self.delivery.id}/status/", {"status": "delivered"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

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

        self.store = Store.objects.create(owner=self.merchant, name="Boutique")
        self.driver = Driver.objects.create(user=self.driver_user)
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
