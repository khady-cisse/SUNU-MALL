"""
Commandes et livraison.
"""
import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.catalog.models import ProductVariant, Store
from apps.users.models import User

from .geoutils import compute_eta_seconds, haversine_km, point_in_polygon


class DeliveryZone(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    boundary_geojson = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def contains(self, lat, lng):
        """Vrai si le point (lat, lng) est dans la frontière de la zone.

        `boundary_geojson` suit la convention GeoJSON simplifiée utilisée
        dans le reste du projet : `{"type": "Polygon", "coordinates": [[[lng, lat], ...]]}`
        (ou une liste "crue" de [lat, lng]). Impossible -> False (la zone
        n'a pas encore de frontière définie par l'admin).
        """
        if lat is None or lng is None:
            return False
        lat, lng = float(lat), float(lng)
        polygon = self._extract_polygon()
        if not polygon:
            return False
        return point_in_polygon(lat, lng, polygon)

    def _extract_polygon(self):
        """Normalise la frontière en une liste de [lat, lng].

        On accepte un FeatureCollection/Feature/Polygon GeoJSON ou une liste
        crue de points. Les coordonnées GeoJSON standard sont [lng, lat] ;
        on les inverse pour `point_in_polygon([lat, lng])`.
        """
        raw = self.boundary_geojson or {}
        if isinstance(raw, dict):
            geometry_type = raw.get("type")
            if geometry_type == "Polygon":
                coords = raw.get("coordinates")
            elif geometry_type == "Feature":
                coords = (raw.get("geometry") or {}).get("coordinates")
            elif geometry_type == "FeatureCollection":
                features = raw.get("features") or []
                coords = ((features[0].get("geometry") or {}) if features else {}).get("coordinates")
            else:
                return None
        elif isinstance(raw, list):
            coords = raw
        else:
            return None

        if not coords or not isinstance(coords[0], list):
            return None
        # Polygone GeoJSON : coords = [[ [lng, lat], ... ]] -> on prend l'anneau extérieur.
        ring = coords[0] if isinstance(coords[0][0], list) else coords
        polygon = [[point[1], point[0]] for point in ring if len(point) >= 2]
        return polygon or None

    def __str__(self):
        return self.name


class Driver(models.Model):
    class AvailabilityStatus(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        BUSY = 'busy', 'Busy'
        OFFLINE = 'offline', 'Offline'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='driver_profile')
    zone = models.ForeignKey(DeliveryZone, on_delete=models.SET_NULL, null=True, related_name='drivers')
    vehicle_type = models.CharField(max_length=100)
    availability_status = models.CharField(max_length=50, choices=AvailabilityStatus.choices, default=AvailabilityStatus.OFFLINE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_available(self):
        return self.availability_status == self.AvailabilityStatus.AVAILABLE

    def current_position(self):
        """Dernière position GPS connue du livreur (toutes courses confondues).

        Le client la reçoit via `DeliverySerializer.last_position` ; cette
        méthode sert au calcul d'ETA (`Delivery.eta_seconds`).
        """
        last_tracking = (
            DeliveryTracking.objects.filter(delivery__driver_id=self.id)
            .order_by("-recorded_at")
            .first()
        )
        return (
            {
                "latitude": last_tracking.latitude,
                "longitude": last_tracking.longitude,
                "recorded_at": last_tracking.recorded_at,
            }
            if last_tracking
            else None
        )

    def __str__(self):
        return f"Driver {self.user.get_full_name()}"


class Delivery(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ASSIGNED = 'assigned', 'Assigned'
        PICKED_UP = 'picked_up', 'Picked Up'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField('Order', on_delete=models.CASCADE, related_name='delivery')
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True, related_name='deliveries')
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def assign_driver(self, driver):
        self.driver = driver
        self.status = self.Status.ASSIGNED
        self.save()
        self._notify_driver_assigned()

    def _notify_driver_assigned(self):
        from apps.monetization.models import Notification

        subject = "Nouvelle course qui vous a été affectée"
        message = (
            f"Bonjour {self.driver.user.first_name},\n\n"
            f"Une nouvelle course vous a été affectée (commande {self.order.id}).\n"
            "Connectez-vous à votre espace livreur pour voir le détail et démarrer la livraison.\n\n"
            "Merci."
        )
        notification = Notification.objects.create(
            user=self.driver.user,
            channel=Notification.Channel.EMAIL,
            subject=subject,
            message=message,
            metadata={"delivery_id": str(self.id), "order_id": str(self.order.id)},
        )
        notification.send()

    def auto_assign(self):
        """
        Affecte automatiquement le livreur disponible ayant le moins de
        courses actives (assigned/picked_up) en ce moment — pour ne pas
        dépendre d'une affectation manuelle à chaque commande, ce qui ne
        tient pas à l'échelle (des centaines de commandes). Ne fait rien
        si un livreur est déjà affecté, ou si aucun n'est disponible : la
        course reste alors "pending", affectable à la main en filet de
        secours (menu déroulant déjà existant côté commerçant/admin).
        """
        if self.driver_id is not None:
            return None

        candidate = (
            Driver.objects.filter(availability_status=Driver.AvailabilityStatus.AVAILABLE)
            .annotate(
                active_count=models.Count(
                    "deliveries",
                    filter=models.Q(deliveries__status__in=[self.Status.ASSIGNED, self.Status.PICKED_UP]),
                )
            )
            .order_by("active_count")
            .first()
        )
        if candidate:
            self.assign_driver(candidate)
        return candidate

    def mark_delivered(self):
        self.status = self.Status.DELIVERED
        self.delivered_at = timezone.now()
        self.save()

    def eta_seconds(self):
        """Temps de trajet estimé (livreur -> adresse du client), en secondes.

        Aucune coordonnée de départ ou d'arrivée -> None (le frontend
        n'affiche alors pas d'ETA plutôt qu'une valeur farfelue).
        """
        if self.status in (self.Status.DELIVERED, self.Status.CANCELLED):
            return 0
        driver_position = self.driver.current_position() if self.driver else None
        if not driver_position or not self.order.address_id:
            return None
        address = self.order.address
        if address.latitude is None or address.longitude is None:
            return None
        return compute_eta_seconds(
            driver_position["latitude"],
            driver_position["longitude"],
            address.latitude,
            address.longitude,
        )

    def event_payload(self, **extra):
        """État courant de la livraison, format diffusé sur le canal temps réel.

        C'est le contrat partagé entre les événements poussés (positions,
        statuts) et l'instantané de connexion SSE : le frontend applique
        chaque événement directement à son écran sans requête supplémentaire.
        """
        last_tracking = self.trackings.first()
        payload = {
            "status": self.status,
            "picked_up_at": self.picked_up_at.isoformat() if self.picked_up_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "eta_seconds": self.eta_seconds(),
            "last_position": (
                {
                    "latitude": str(last_tracking.latitude),
                    "longitude": str(last_tracking.longitude),
                    "recorded_at": last_tracking.recorded_at.isoformat(),
                }
                if last_tracking
                else None
            ),
            "message": "",
        }
        payload.update(extra)
        return payload

    def broadcast_status(self, message=""):
        """Diffuse le changement de statut en temps réel sur le canal livraison.

        Chaque transition du CDC (récupérée, en route, livrée, annulée) arrive
        ainsi instantanément à l'écran du client, en plus de l'email existant.
        """
        from .realtime import publish_delivery_event

        self.refresh_from_db(fields=["driver", "status", "picked_up_at", "delivered_at"])
        publish_delivery_event(self.id, "status", self.event_payload(message=message))

    def cancel(self):
        """Annule la course (appelé quand le client annule sa commande) et prévient le livreur s'il en avait déjà un."""
        had_driver = self.driver_id is not None
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status"])
        self.broadcast_status("La livraison de votre commande a été annulée.")
        if had_driver:
            self._notify_driver_cancelled()

    def _notify_driver_cancelled(self):
        from apps.monetization.models import Notification

        subject = "Course annulée"
        message = (
            f"Bonjour {self.driver.user.first_name},\n\n"
            f"La commande {str(self.order.id)[:8]} qui vous avait été affectée vient d'être annulée "
            "par le client. Vous n'avez plus besoin d'intervenir sur cette livraison.\n\n"
            "Merci."
        )
        notification = Notification.objects.create(
            user=self.driver.user,
            channel=Notification.Channel.EMAIL,
            subject=subject,
            message=message,
            metadata={"delivery_id": str(self.id), "order_id": str(self.order.id)},
        )
        notification.send()

    def __str__(self):
        return f"Delivery for Order {self.order.id}"


class DeliveryTracking(models.Model):
    id = models.AutoField(primary_key=True)
    delivery = models.ForeignKey(Delivery, on_delete=models.CASCADE, related_name='trackings')
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']

    def broadcast(self):
        """Publie la nouvelle position sur le canal temps réel de la livraison.

        Appelé après l'enregistrement d'un point GPS (voir `DeliveryViewSet.track`) :
        le client a déjà `.delivery` et `.driver_detail` à l'écran, il ne lui
        manque que la position à jour — d'où uniquement la géolocalisation
        ici, pas tout le payload de la livraison.
        """
        from .realtime import publish_delivery_event

        publish_delivery_event(
            self.delivery_id,
            "position",
            self.delivery.event_payload(
                last_position={
                    "latitude": str(self.latitude),
                    "longitude": str(self.longitude),
                    "recorded_at": self.recorded_at.isoformat(),
                }
            ),
        )

    def __str__(self):
        return f"Tracking {self.delivery.id} at {self.recorded_at}"


class Address(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=255)
    street = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='Senegal')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def distance_to(self, lat, lng):
        """Distance à vol d'oiseau (km) vers un autre point, ou None sans coordonnées."""
        if self.latitude is not None and self.longitude is not None and lat is not None and lng is not None:
            return haversine_km(self.latitude, self.longitude, lat, lng)
        return None

    def __str__(self):
        return f"{self.label} for {self.user.get_full_name()}"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        PROCESSING = 'processing', 'Processing'
        SHIPPED = 'shipped', 'Shipped'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='orders')
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, related_name='orders')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def can_be_cancelled(self):
        return self.status in [self.Status.PENDING, self.Status.PAID]

    def recalculate_total(self):
        self.total_amount = sum(item.subtotal() for item in self.items.all()) + self.delivery_fee
        self.save()

    def change_status(self, new_status):
        old_status = self.status
        self.status = new_status
        self.save()
        OrderHistory.objects.create(
            order=self,
            previous_status=old_status,
            new_status=new_status,
            changed_by=self.customer
        )
        from apps.analytics.models import SalesStatistic
        SalesStatistic.compute_for_store(self.store, self.created_at.date())

    def notify_merchant_cancelled(self):
        from apps.monetization.models import Notification

        subject = f"Commande annulée — {self.store.name}"
        message = (
            f"Bonjour,\n\n"
            f"La commande n°{str(self.id)[:8]} ({self.total_amount} FCFA) vient d'être annulée par le client.\n\n"
            "Consultez votre tableau de bord pour plus de détails."
        )
        notification = Notification.objects.create(
            user=self.store.owner,
            channel=Notification.Channel.EMAIL,
            subject=subject,
            message=message,
            metadata={"order_id": str(self.id)},
        )
        notification.send()

    def __str__(self):
        return f"Order {self.id} - {self.customer.email}"


class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='order_items')
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def subtotal(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.quantity} x {self.product_variant.product.name}"


class OrderHistory(models.Model):
    id = models.AutoField(primary_key=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='history')
    previous_status = models.CharField(max_length=50, blank=True)
    new_status = models.CharField(max_length=50)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='order_changes')
    changed_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"Order {self.order.id}: {self.previous_status} → {self.new_status}"
