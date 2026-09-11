"""
Commandes et livraison + partenaires logistiques (Espace Partenaire).

Le système de livraison de SUNU MALL fonctionne avec des entreprises
logistiques partenaires (DeliveryPartner) qui emploient chacune leurs
livreurs (Driver). Une livraison (Delivery) est affectée à un partenaire
puis à un livreur ; chaque transition de statut est tracée dans
DeliveryEvent (traçabilité complète, spec §28).
"""
import hashlib
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
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


class DeliveryPartner(models.Model):
    """Entreprise de livraison partenaire (Espace Partenaire, spec §3).

    Sunu Mall ne possède pas sa propre flotte : elle connecte un ou plusieurs
    partenaires logistiques. Chaque partenaire emploie ses propres livreurs et
    ne voit jamais les données des autres partenaires (isolation stricte,
    spec §24).
    """

    class Status(models.TextChoices):
        INACTIVE = "inactive", "Inactif"
        ACTIVE = "active", "Actif"
        SUSPENDED = "suspended", "Suspendu"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Compte utilisateur (rôle `partner`) qui pilote l'Espace Partenaire ;
    # l'admin lie l'entreprise à un compte après activation (spec §2, §11).
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='partner_profile'
    )
    name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INACTIVE)
    # Score automatique (0-100) basé sur taux de réussite, SLA, retours, etc.
    # Recalculé périodiquement (ou à la volée) — voir `compute_score`.
    score = models.PositiveSmallIntegerField(default=0)
    # Clé d'API pour les échanges machine ↔ machine (spec §23). Seul le hash
    # est stocké ; le clair n'est rendu qu'une fois à la génération.
    api_key_hash = models.CharField(max_length=64, blank=True, default="")
    api_key_last4 = models.CharField(max_length=4, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.status})"

    def is_active(self):
        return self.status == self.Status.ACTIVE

    def active_drivers(self):
        return self.drivers.filter(is_suspended=False)

    def delivery_count(self):
        return self.deliveries.count()

    def delivered_count(self):
        return self.deliveries.filter(status=Delivery.Status.DELIVERED).count()

    def success_rate(self, days=90):
        """Taux de livraisons réussies sur les N derniers jours (0-100)."""
        cutoff = timezone.now() - timedelta(days=days)
        base = self.deliveries.filter(created_at__gte=cutoff)
        delivered = base.filter(status=Delivery.Status.DELIVERED).count()
        failed = base.filter(
            status__in=[Delivery.Status.DELIVERY_FAILED, Delivery.Status.CUSTOMER_UNAVAILABLE]
        ).count()
        settled = delivered + failed
        if settled == 0:
            return 100.0
        return round(delivered / settled * 100, 1)

    def return_rate(self, days=90):
        cutoff = timezone.now() - timedelta(days=days)
        base = self.deliveries.filter(created_at__gte=cutoff)
        total = base.count()
        if total == 0:
            return 0.0
        returned = base.filter(status=Delivery.Status.RETURNED).count()
        return round(returned / total * 100, 1)

    def avg_delay_minutes(self, days=90):
        """Délai moyen (affectation -> livraison) des livraisons réussies, en minutes."""
        cutoff = timezone.now() - timedelta(days=days)
        delivered = self.deliveries.filter(status=Delivery.Status.DELIVERED, delivered_at__isnull=False).filter(
            created_at__gte=cutoff
        )
        total = 0
        count = 0
        for delivery in delivered:
            if delivery.assigned_at:
                total += (delivery.delivered_at - delivery.assigned_at).total_seconds() / 60
                count += 1
        return round(total / count, 1) if count else 0.0

    def compute_score(self, days=90):
        """Score automatique 0-100 basé sur la performance récente.

        Pondération : réussite (50), délais/SLA (25), retours (15), échecs (10).
        Aucun historique -> score neutre (100) plutôt que 0 pour ne pas
        pénaliser une entreprise tout juste intégrée.
        """
        cutoff = timezone.now() - timedelta(days=days)
        base = self.deliveries.filter(created_at__gte=cutoff)
        total = base.count()
        if total == 0:
            self.score = 100
            self.save(update_fields=["score"])
            return 100

        delivered = base.filter(status=Delivery.Status.DELIVERED).count()
        failed = base.filter(
            status__in=[Delivery.Status.DELIVERY_FAILED, Delivery.Status.CUSTOMER_UNAVAILABLE]
        ).count()
        returned = base.filter(status=Delivery.Status.RETURNED).count()

        success_score = 50.0 * (delivered / total)
        failure_score = 10.0 * (1 - failed / total)
        return_score = 15.0 * (1 - returned / total)

        avg_delay = self.avg_delay_minutes(days)
        on_time_score = 25.0
        if avg_delay > 0:
            expected = self._expected_delay_minutes()
            ratio = max(0.0, min(1.0, expected / avg_delay if avg_delay else 1))
            on_time_score = 25.0 * ratio

        score = round(success_score + failure_score + return_score + on_time_score)
        score = max(0, min(100, score))
        self.score = score
        self.save(update_fields=["score"])
        return score

    def _expected_delay_minutes(self):
        """Délai contractuel moyen (min des délais déclarés sur les zones couvertes)."""
        delays = list(
            self.zone_pricings.filter(is_available=True, estimated_delay_minutes__gt=0)
            .values_list("estimated_delay_minutes", flat=True)
        )
        return float(min(delays)) if delays else 60.0

    def covers_zone(self, zone):
        if not zone or not self.is_active():
            return False
        return self.zone_pricings.filter(zone=zone, is_available=True).exists()

    def partner_cost_for(self, delivery):
        """Coût payé au partenaire pour une livraison donnée (tarif zone §22).

        Le coût est figé au moment du calcul à partir de la zone correspondant
        à l'adresse de livraison ; 0 si aucune zone tarifée ne couvre la course.
        """
        address = delivery.target_address()
        if address is None:
            return Decimal("0")
        pk_list = self.zone_pricings.filter(is_available=True).values_list("id", flat=True)
        for pricing_id in pk_list:
            p = self.zone_pricings.select_related("zone").get(id=pricing_id)
            if p.zone.contains(address.latitude, address.longitude):
                return p.partner_cost
        return Decimal("0")

    def rotate_api_key(self):
        """Génère une nouvelle clé d'API ; seul le hash est conservé."""
        raw = f"sm_{secrets.token_urlsafe(32)}"
        self.api_key_hash = hashlib.sha256(raw.encode()).hexdigest()
        self.api_key_last4 = raw[-4:]
        self.save(update_fields=["api_key_hash", "api_key_last4"])
        return raw

    def check_api_key(self, raw):
        if not raw or not self.api_key_hash:
            return False
        candidate = hashlib.sha256(raw.encode()).hexdigest()
        return secrets.compare_digest(candidate, self.api_key_hash)


class PartnerZonePricing(models.Model):
    """Tarification d'un partenaire pour une zone (spec §21, §22).

    Sunu Mall utilise `client_fee` pour facturer le client (frais de
    livraison) et paie `partner_cost` au partenaire ; la marge Sunu Mall est
    la différence, calculée côté serveur uniquement.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    partner = models.ForeignKey(DeliveryPartner, on_delete=models.CASCADE, related_name="zone_pricings")
    zone = models.ForeignKey(DeliveryZone, on_delete=models.CASCADE, related_name="partner_pricings")
    client_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("2000"))
    partner_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1500"))
    estimated_delay_minutes = models.PositiveIntegerField(default=60)
    max_weight_kg = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("20"))
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["zone__name"]
        unique_together = ["partner", "zone"]

    @property
    def margin(self):
        return self.client_fee - self.partner_cost

    def __str__(self):
        return f"{self.partner.name} — {self.zone.name}"


class Driver(models.Model):
    class AvailabilityStatus(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        BUSY = 'busy', 'Busy'
        OFFLINE = 'offline', 'Offline'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='driver_profile')
    # Le livreur appartient à un seul partenaire actif (spec §2, §30). Sans
    # partenaire, il reste affectable manuellement (rétrocompatibilité).
    partner = models.ForeignKey(
        DeliveryPartner, on_delete=models.SET_NULL, null=True, blank=True, related_name='drivers'
    )
    zone = models.ForeignKey(DeliveryZone, on_delete=models.SET_NULL, null=True, related_name='drivers')
    vehicle_type = models.CharField(max_length=100)
    availability_status = models.CharField(max_length=50, choices=AvailabilityStatus.choices, default=AvailabilityStatus.OFFLINE)
    # Livreur suspendu : ne peut plus recevoir ni accepter de missions mais
    # son historique est conservé (statut SUSPENDU, spec §7).
    is_suspended = models.BooleanField(default=False)
    # Capacité : nombre maximal de livraisons actives simultanées (§7).
    max_active_deliveries = models.PositiveSmallIntegerField(default=2)
    # Position "libre" du livreur (hors course) : communiquée quand il se rend
    # disponible, elle sert à vérifier qu'il est proche de la boutique avant
    # de lui affecter une course (affectation = proximité géographique).
    last_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    position_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def is_available(self):
        return not self.is_suspended and self.availability_status == self.AvailabilityStatus.AVAILABLE

    def active_deliveries_count(self):
        """Nombre de livraisons en cours (non terminées) du livreur."""
        return self.deliveries.exclude(
            status__in=[
                Delivery.Status.DELIVERED, Delivery.Status.DELIVERY_FAILED,
                Delivery.Status.CUSTOMER_UNAVAILABLE, Delivery.Status.RETURNED,
                Delivery.Status.CANCELLED,
            ]
        ).count()

    def can_take_more(self):
        return self.active_deliveries_count() < self.max_active_deliveries

    def success_rate(self, days=90):
        """Taux de réussite du livreur sur les N derniers jours (0-100)."""
        cutoff = timezone.now() - timedelta(days=days)
        base = self.deliveries.filter(created_at__gte=cutoff)
        delivered = base.filter(status=Delivery.Status.DELIVERED).count()
        failed = base.filter(
            status__in=[Delivery.Status.DELIVERY_FAILED, Delivery.Status.CUSTOMER_UNAVAILABLE]
        ).count()
        settled = delivered + failed
        if settled == 0:
            return 100.0
        return round(delivered / settled * 100, 1)

    def position(self):
        """Coordonnées libres (lat, lng) du livreur, ou None sans position."""
        if self.last_latitude is not None and self.last_longitude is not None:
            return (self.last_latitude, self.last_longitude)
        return None

    def distance_to_store_km(self, store):
        """Distance à vol d'oiseau (km) entre le livreur et une boutique.

        None si le livreur n'a pas de position libre, ou si la boutique n'a
        pas de coordonnées GPS.
        """
        pos = self.position()
        if pos is None or store.latitude is None or store.longitude is None:
            return None
        return haversine_km(pos[0], pos[1], store.latitude, store.longitude)

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
        ACCEPTED = 'accepted', 'Accepted'
        PICKUP_PENDING = 'pickup_pending', 'Pickup Pending'
        PICKED_UP = 'picked_up', 'Picked Up'
        IN_TRANSIT = 'in_transit', 'In Transit'
        OUT_FOR_DELIVERY = 'out_for_delivery', 'Out For Delivery'
        DELIVERED = 'delivered', 'Delivered'
        DELIVERY_FAILED = 'delivery_failed', 'Delivery Failed'
        CUSTOMER_UNAVAILABLE = 'customer_unavailable', 'Customer Unavailable'
        RETURN_REQUESTED = 'return_requested', 'Return Requested'
        RETURNED = 'returned', 'Returned'
        CANCELLED = 'cancelled', 'Cancelled'

    class FailureReason(models.TextChoices):
        CUSTOMER_ABSENT = 'customer_absent', 'Client absent'
        NUMBER_UNREACHABLE = 'number_unreachable', 'Numéro inaccessible'
        WRONG_ADDRESS = 'wrong_address', 'Mauvaise adresse'
        CUSTOMER_REFUSED = 'customer_refused', 'Client refuse'
        PACKAGE_DAMAGED = 'package_damaged', 'Colis endommagé'
        TRANSPORT_ISSUE = 'transport_issue', 'Problème de transport'
        OTHER = 'other', 'Autre'

    class ProofMethod(models.TextChoices):
        OTP = 'otp', 'OTP'
        SIGNATURE = 'signature', 'Signature'
        PHOTO = 'photo', 'Photo'
        CLIENT_CONFIRMATION = 'client_confirmation', 'Confirmation client'

    class ReturnReason(models.TextChoices):
        CUSTOMER_ABSENT = 'customer_absent', 'Client absent'
        CUSTOMER_REFUSED = 'customer_refused', 'Client refuse'
        WRONG_ADDRESS = 'wrong_address', 'Mauvaise adresse'
        PACKAGE_DAMAGED = 'package_damaged', 'Colis endommagé'
        SHIPPING_ERROR = 'shipping_error', 'Erreur d\'envoi'
        OTHER = 'other', 'Autre'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Référence lisible DLV-YYYYMMDD-XXXXXX (spec §5), générée automatiquement.
    reference = models.CharField(max_length=30, unique=True, blank=True, default="")
    # Une livraison « classique » est liée à une seule commande (`order`).
    # Une mission multi-boutiques est liée à une commande globale
    # (`global_order`) et décrite par ses points de collecte (DeliveryPickup) :
    # `order` est alors vide. Les deux références sont mutuellement exclusives.
    order = models.OneToOneField('Order', on_delete=models.CASCADE, related_name='delivery', null=True, blank=True)
    global_order = models.ForeignKey(
        'GlobalOrder', on_delete=models.CASCADE, related_name='deliveries', null=True, blank=True
    )
    # Totaux financiers et physiques de la mission (spec multi-boutiques §7).
    # `total_delivery_fee` est le montant facturé au client (Order.delivery_fee
    # côté sous-commandes reste à 0 : le client paie une fois, globalement) ;
    # `partner_cost` est le coût payé au partenaire et `platform_margin` la
    # marge Sunu Mall, calculés côté serveur uniquement.
    total_delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    partner_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    platform_margin = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_distance = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    total_weight = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    total_volume = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    estimated_duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    # Partenaire logistique en charge de la course (spec §2). Affecté
    # automatiquement à la commande ou manuellement par un admin.
    partner = models.ForeignKey(
        DeliveryPartner, on_delete=models.SET_NULL, null=True, blank=True, related_name='deliveries'
    )
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True, related_name='deliveries')
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING)
    # Horodatage de chaque étape de la timeline (spec §28). `picked_up_at` et
    # `delivered_at` existaient déjà ; on garde ces noms pour la rétrocompat.
    assigned_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    in_transit_at = models.DateTimeField(null=True, blank=True)
    out_for_delivery_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    return_requested_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    # Motif d'échec / de refus / de retour (spec §16, §17).
    failure_reason = models.CharField(max_length=50, choices=FailureReason.choices, blank=True, default="")
    failure_comment = models.TextField(blank=True, default="")
    return_reason = models.CharField(max_length=50, choices=ReturnReason.choices, blank=True, default="")
    refuse_reason = models.CharField(max_length=50, blank=True, default="")
    # Preuve de livraison (spec §15) : méthode, référence (photo/signature),
    # géolocalisation autorisée et commentaire.
    proof_method = models.CharField(max_length=30, choices=ProofMethod.choices, blank=True, default="")
    proof_note = models.TextField(blank=True, default="")
    proof_photo = models.CharField(max_length=500, blank=True, default="")
    proof_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    proof_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    proof_recorded_at = models.DateTimeField(null=True, blank=True)
    confirmation_otp_hash = models.CharField(max_length=64, blank=True, default="")
    confirmation_otp_expires_at = models.DateTimeField(null=True, blank=True)
    confirmation_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def next_reference(cls):
        """Génère la prochaine référence DLV-YYYYMMDD-XXXXXX de la journée."""
        today = timezone.localdate()
        prefix = f"DLV-{today.strftime('%Y%m%d')}-"
        last = (
            cls.objects.filter(reference__startswith=prefix)
            .order_by("-reference")
            .values_list("reference", flat=True)
            .first()
        )
        sequence = int(last.split("-")[-1]) + 1 if last else 1
        return f"{prefix}{sequence:06d}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self.next_reference()
        super().save(*args, **kwargs)

    def record_event(self, action, user=None, actor_role="", previous_status=None,
                     new_status=None, comment="", metadata=None):
        """Trace une étape de la timeline de la livraison (spec §28).

        Chaque événement enregistre l'acteur, son rôle, l'action, l'ancienne et
        la nouvelle valeur, le commentaire et une référence (la livraison).
        """
        from apps.users.models import Role

        if not actor_role and user and user.is_authenticated:
            first_role = user.user_roles.select_related("role").first()
            actor_role = first_role.role.name if first_role else ""
        return DeliveryEvent.objects.create(
            delivery=self,
            actor=user if (user and user.is_authenticated) else None,
            actor_role=actor_role,
            action=action,
            previous_status=previous_status or self.status,
            new_status=new_status or self.status,
            comment=comment,
            metadata=metadata or {},
        )

    def assign_partner(self, partner, user=None):
        """Affecte l'entreprise partenaire responsable de la course."""
        if self.status != self.Status.PENDING:
            return
        old = self.status
        self.partner = partner
        self.status = self.Status.ASSIGNED
        self.assigned_at = timezone.now()
        self.save()
        self.record_event(
            "pending→assigned", user=user, actor_role="admin",
            previous_status=old, new_status=self.status,
            metadata={"partner": str(partner.id) if partner else None},
        )
        if partner:
            self._notify_partner_new_delivery()

    @property
    def is_multi_store(self):
        return self.global_order_id is not None

    def linked_orders(self):
        """Sous-commandes couvertes par cette mission.

        Retourne un QuerySet : la commande simple pour une livraison
        classique, toutes les sous-commandes pour une mission multi-boutiques.
        """
        from .models import Order

        if self.global_order_id:
            return Order.objects.filter(global_order_id=self.global_order_id)
        return Order.objects.filter(pk=self.order_id)

    def target_address(self):
        """Adresse de destination du client pour cette mission."""
        return self.global_order.address if self.is_multi_store else self.order.address if self.order_id else None

    def target_customer(self):
        return self.global_order.customer if self.is_multi_store else self.order.customer if self.order_id else None

    def main_store(self):
        """Boutique de référence (1er point de collecte, sinon la boutique simple)."""
        first = self.pickups.order_by("pickup_order").first()
        if first:
            return first.store
        return self.order.store if self.order_id else None

    def pickups_status(self):
        """Statut agrégé des points de collecte : (récupérés, total, tous faits ?)."""
        total = self.pickups.count()
        done = self.pickups.filter(pickup_status=DeliveryPickup.Status.PICKED_UP).count()
        return done, total, total > 0 and done == total

    def _notify_partner_new_delivery(self):
        """Prévient l'entreprise partenaire qu'une course lui est confiée.

        Si le compte utilisateur du partenaire est lié (Espace Partenaire),
        un Notification interne est créée ; sinon on retombe sur un email
        direct au contact (jamais bloquant).
        """
        message = (
            f"Bonjour,\n\nUne nouvelle livraison ({self.reference}) vous est confiée "
            f"pour la commande {str(self.order_id or self.global_order_id)[:8]}.\n"
            "Connectez-vous à votre Espace Partenaire pour affecter un livreur.\n\n"
            "Merci."
        )
        partner = self.partner
        if partner and partner.user_id:
            from apps.monetization.models import Notification

            Notification.objects.create(
                user=partner.user,
                channel=Notification.Channel.EMAIL,
                subject="Nouvelle livraison à traiter",
                message=message,
                metadata={"delivery_ref": self.reference, "partner": str(partner.id)},
            ).send()
        elif partner and partner.contact_email:
            from django.core.mail import send_mail

            send_mail(
                "Nouvelle livraison à traiter",
                message,
                settings.DEFAULT_FROM_EMAIL,
                [partner.contact_email],
                fail_silently=True,
            )

    def assign_driver(self, driver, user=None):
        """Affecte un livreur à la livraison (par le partenaire ou un admin).

        La course reste « assigned » tant que le livreur n'a pas accepté la
        mission. Renvoie la livraison pour chaîner.
        """
        old = self.status
        self.driver = driver
        self.status = self.Status.ASSIGNED
        if self.assigned_at is None:
            self.assigned_at = timezone.now()
        if self.partner_id is None and driver and driver.partner_id:
            self.partner_id = driver.partner_id
        self.save()
        self.record_event(
            "assigned", user=user, actor_role="partner" if user and user.is_partner() else "admin",
            previous_status=old, new_status=self.status,
            metadata={"driver": str(driver.id) if driver else None},
        )
        self._notify_driver_assigned()
        return self

    def _notify_driver_assigned(self):
        from apps.monetization.models import Notification

        subject = "Nouvelle mission qui vous est affectée"
        message = (
            f"Bonjour {self.driver.user.first_name},\n\n"
            f"Une nouvelle mission vous est affectée — livraison {self.reference} "
            f"(commande {str(self.order_id or self.global_order_id)[:8]}).\n"
            "Connectez-vous à votre espace livreur pour accepter et démarrer.\n\n"
            "Merci."
        )
        Notification.objects.create(
            user=self.driver.user,
            channel=Notification.Channel.EMAIL,
            subject=subject,
            message=message,
            metadata={"delivery_id": str(self.id), "order_id": str(self.order_id or self.global_order_id)},
        ).send()

    def auto_assign(self):
        """Affecte automatiquement le meilleur livreur disponible.

        Si un partenaire est en charge, la sélection se fait parmi SES livreurs
        (sinon parmi tous). Rang : dispo, capacité restante, proximité de la
        boutique, charge actuelle. Ne fait rien si aucun n'est disponible.
        """
        if self.driver_id is not None:
            return None
        driver = self.suggested_driver()
        if driver:
            self.assign_driver(driver)
        return driver

    def suggested_driver(self, limit=5):
        """Meilleurs livreurs candidats (spec §7) — proximité, zone, dispo, charge."""
        store = self.main_store()
        queryset = Driver.objects.filter(
            availability_status=Driver.AvailabilityStatus.AVAILABLE,
            is_suspended=False,
        )
        if self.partner_id:
            queryset = queryset.filter(partner_id=self.partner_id)
        queryset = queryset.annotate(
            active_count=models.Count(
                "deliveries",
                filter=models.Q(
                    deliveries__status__in=[
                        self.Status.ASSIGNED, self.Status.ACCEPTED, self.Status.PICKUP_PENDING,
                        self.Status.PICKED_UP, self.Status.IN_TRANSIT, self.Status.OUT_FOR_DELIVERY,
                    ]
                ),
            )
        ).order_by("active_count")
        candidates = list(queryset[:limit])
        if not candidates:
            return None
        candidates.sort(
            key=lambda d: (
                not d.can_take_more(),
                d.distance_to_store_km(store) if d.distance_to_store_km(store) is not None else 9999,
                d.active_deliveries_count,
                d.success_rate(),
            )
        )
        return candidates[0] if candidates[0].can_take_more() else candidates[0]

    def notify_assigned_partner(self, user=None):
        """Sert au flux d'acceptation : notification/suivi après affectation."""
        self.record_event("assigned", user=user)

    def assign(self, driver_id, user):
        return self.assign_driver(driver_id, user)

    def _transition_to(self, new_status, user=None, actor_role="", comment="", metadata=None):
        """Applique une transition de statut et la trace."""
        old = self.status
        self.status = new_status
        now = timezone.now()
        stamps = {
            self.Status.ASSIGNED: "assigned_at",
            self.Status.ACCEPTED: "accepted_at",
            self.Status.PICKED_UP: "picked_up_at",
            self.Status.IN_TRANSIT: "in_transit_at",
            self.Status.OUT_FOR_DELIVERY: "out_for_delivery_at",
            self.Status.DELIVERED: "delivered_at",
            self.Status.DELIVERY_FAILED: "failed_at",
            self.Status.CUSTOMER_UNAVAILABLE: "failed_at",
            self.Status.RETURN_REQUESTED: "return_requested_at",
            self.Status.RETURNED: "returned_at",
            self.Status.CANCELLED: "cancelled_at",
        }
        field = stamps.get(new_status)
        if field:
            setattr(self, field, now)
        self.save()
        self.record_event(
            "status_changed", user=user, actor_role=actor_role,
            previous_status=old, new_status=new_status,
            comment=comment, metadata=metadata or {},
        )
        return old

    def accept(self, user):
        if self.status != self.Status.ASSIGNED:
            raise ValueError("La mission doit être affectée avant d'être acceptée.")
        if self.driver and self.driver.user_id != user.id:
            raise PermissionError("Seul le livreur affecté peut accepter cette mission.")
        self._transition_to(self.Status.ACCEPTED, user=user, actor_role="driver", comment="Mission acceptée")
        self.broadcast_status(f"{self.reference} : mission acceptée par le livreur.")

    def refuse(self, user, reason, comment=""):
        """Le livreur refuse la mission : la livraison redevient affectable."""
        if self.status != self.Status.ASSIGNED:
            raise ValueError("La mission doit être affectée pour être refusée.")
        if self.driver and self.driver.user_id != user.id:
            raise PermissionError("Seul le livreur affecté peut refuser cette mission.")
        self.refuse_reason = reason
        self.failure_comment = comment or self.failure_comment
        driver = self.driver
        old_status = self.status
        self.driver = None
        self.status = self.Status.ASSIGNED
        self.save()
        DeliveryEvent.objects.create(
            delivery=self,
            actor=user,
            actor_role="driver",
            action="refused",
            previous_status=old_status,
            new_status=self.status,
            comment=f"Refus ({reason}) : {comment}".strip(),
        )
        # La course reste affectable : tentative d'auto-réaffectation (§29).
        if self.partner_id:
            self.auto_assign()

    def mark_delivered(self, user=None, actor_role="", proof_method="", proof_note="",
                       latitude=None, longitude=None):
        self.proof_method = proof_method or self.ProofMethod.CLIENT_CONFIRMATION
        self.proof_note = proof_note or self.proof_note
        self.proof_latitude = latitude or self.proof_latitude
        self.proof_longitude = longitude or self.proof_longitude
        self.proof_recorded_at = timezone.now()
        self.confirmation_otp_hash = ""
        self.confirmation_otp_expires_at = None
        self._transition_to(self.Status.DELIVERED, user=user, actor_role=actor_role,
                            comment="Livraison confirmée.")
        for order in self.linked_orders():
            order.change_status(Order.Status.DELIVERED, changed_by=user or order.customer)
        return self

    def mark_failed(self, user=None, actor_role="driver", reason=None, comment="", latitude=None, longitude=None):
        if reason not in self.FailureReason.values:
            raise ValueError("Motif d'échec obligatoire.")
        self.failure_reason = reason
        self.failure_comment = comment
        new_status = (
            self.Status.CUSTOMER_UNAVAILABLE if reason == self.FailureReason.CUSTOMER_ABSENT
            else self.Status.DELIVERY_FAILED
        )
        self._transition_to(new_status, user=user, actor_role=actor_role,
                            comment=f"{comment} Motif : {reason}".strip())
        self.broadcast_status("Livraison signalée comme échouée par le livreur.")

    def request_return(self, user=None, actor_role="driver", reason=None, comment=""):
        if reason and reason not in self.ReturnReason.values:
            raise ValueError("Motif de retour invalide.")
        self.return_reason = reason or self.return_reason
        self._transition_to(self.Status.RETURN_REQUESTED, user=user, actor_role=actor_role,
                            comment=f"Retour demandé{(' : ' + reason) if reason else ''}")
        return self

    def mark_returned(self, user=None, actor_role="driver", comment=""):
        self._transition_to(self.Status.RETURNED, user=user, actor_role=actor_role,
                            comment=comment or "Colis retourné au vendeur.")
        self.broadcast_status("Le colis a été retourné au vendeur.")

    def cancel(self, user=None, comment=""):
        """Annule la course (appelé quand le client annule sa commande) et prévient le livreur s'il en avait déjà un."""
        had_driver = self.driver_id is not None
        parent = None
        if self.status != self.Status.CANCELLED:
            parent = self._transition_to(self.Status.CANCELLED, user=user, actor_role="admin",
                                         comment=comment or "Annulation")
        self.broadcast_status("La livraison de votre commande a été annulée.")
        if had_driver:
            self._notify_driver_cancelled()
        return parent

    def generate_confirmation_otp(self):
        """Génère un code de confirmation à 6 chiffres pour la remise au client.

        Le code en clair n'est stocké nulle part (seul son hash SHA-256 est
        conservé) ; il n'est rendu qu'une seule fois à l'appelant (le livreur
        qui fait progresser la course, ou l'action `regenerate-otp`). Valide
        30 minutes et limité à `MAX_OTP_ATTEMPTS` essais de saisie.
        """
        code = f"{secrets.randbelow(1_000_000):06d}"
        self.confirmation_otp_hash = hashlib.sha256(code.encode()).hexdigest()
        self.confirmation_otp_expires_at = timezone.now() + timedelta(
            minutes=int(settings.CONFIRMATION_OTP_TTL_MINUTES)
        )
        self.confirmation_attempts = 0
        self.save(update_fields=["confirmation_otp_hash", "confirmation_otp_expires_at", "confirmation_attempts"])
        return code

    def validate_confirmation_otp(self, code):
        """Vérifie le code saisi par le client contre le hash stocké.

        Incrémente le compteur d'essais en cas d'échec ; un code expiré ou
        un épuisement des essais invalide définitivement ce code (le livreur
        devra en générer un nouveau).
        """
        if (
            not code
            or not self.confirmation_otp_hash
            or not self.confirmation_otp_expires_at
            or self.confirmation_attempts >= settings.MAX_OTP_ATTEMPTS
            or timezone.now() > self.confirmation_otp_expires_at
        ):
            return False
        candidate = hashlib.sha256(str(code).strip().encode()).hexdigest()
        if not secrets.compare_digest(candidate, self.confirmation_otp_hash):
            self.confirmation_attempts = self.confirmation_attempts + 1
            self.save(update_fields=["confirmation_attempts"])
            return False
        return True

    def eta_seconds(self):
        """Temps de trajet estimé (livreur -> adresse du client), en secondes.

        Aucune coordonnée de départ ou d'arrivée -> None (le frontend
        n'affiche alors pas d'ETA plutôt qu'une valeur farfelue).
        """
        if self.status in (self.Status.DELIVERED, self.Status.CANCELLED):
            return 0
        driver_position = self.driver.current_position() if self.driver else None
        address = self.target_address()
        if not driver_position or address is None:
            return None
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

    def cancel(self, user=None, comment=""):
        """Annule la course (appelé quand le client annule sa commande) et prévient le livreur s'il en avait déjà un."""
        had_driver = self.driver_id is not None
        if self.status != self.Status.CANCELLED:
            self._transition_to(self.Status.CANCELLED, user=user, actor_role="admin",
                                comment=comment or "Annulation")
        self.broadcast_status("La livraison de votre commande a été annulée.")
        if had_driver:
            self._notify_driver_cancelled()

    def _notify_driver_cancelled(self):
        from apps.monetization.models import Notification

        subject = "Course annulée"
        message = (
            f"Bonjour {self.driver.user.first_name},\n\n"
            f"La commande {str(self.order_id or self.global_order_id)[:8]} qui vous avait été affectée vient d'être annulée "
            "par le client. Vous n'avez plus besoin d'intervenir sur cette livraison.\n\n"
            "Merci."
        )
        notification = Notification.objects.create(
            user=self.driver.user,
            channel=Notification.Channel.EMAIL,
            subject=subject,
            message=message,
            metadata={"delivery_id": str(self.id), "order_id": str(self.order_id or self.global_order_id)},
        )
        notification.send()

    def __str__(self):
        ref = self.order_id or self.global_order_id
        return f"Delivery for Order {ref}"


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
    # Quand la commande fait partie d'un achat multi-boutiques, elle est la
    # « sous-commande » d'une commande globale (GlobalOrder). Les commandes
    # classiques (une boutique) conservent `global_order = None`.
    global_order = models.ForeignKey(
        'GlobalOrder', on_delete=models.CASCADE, related_name='orders', null=True, blank=True
    )
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, related_name='orders')
    # Type de livraison choisi par le client (spec §5). Persisté pour l'audit
    # et le calcul du tarif (la valeur ne vient jamais du frontend pour le
    # calcul : le montant est toujours recalculé côté serveur).
    delivery_type = models.CharField(
        max_length=20, choices=[('pickup', 'pickup'), ('standard', 'standard'), ('express', 'express')],
        default='standard', blank=True,
    )
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

    def change_status(self, new_status, changed_by=None):
        old_status = self.status
        self.status = new_status
        self.save()
        OrderHistory.objects.create(
            order=self,
            previous_status=old_status,
            new_status=new_status,
            changed_by=changed_by or self.customer,
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


class DeliveryEvent(models.Model):
    """Étape de la timeline d'une livraison (spec §28).

    Horizon temporel complet : chaque changement de statut, affectation, refus,
    échec, retour, preuve, d'acteur (admin/partenaire/livreur/client) et le
    commentaire associé, horodatés. Sert d'audit et alimente la frise affichée
    dans l'Espace Partenaire.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery = models.ForeignKey(Delivery, on_delete=models.CASCADE, related_name='events')
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='delivery_events'
    )
    actor_role = models.CharField(max_length=30, default="", blank=True)
    action = models.CharField(max_length=50)
    previous_status = models.CharField(max_length=50, default="", blank=True)
    new_status = models.CharField(max_length=50, default="", blank=True)
    comment = models.TextField(default="", blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.delivery.reference} : {self.action}"


class PartnerInvoice(models.Model):
    """Facture d'un partenaire (spec §19-§22).

    Établie sur une période, à partir des livraisons DELIVERED/MARKETPLACE
    payées à ce partenaire. `total_due` = somme des courses facturables,
    `collection_fees` = commission prélevée par Sunu Mall, `balance` =
    montant net à régler. La réconciliation (spec §21) compare le total des
    course facturables à la période (recompute) au montant retenu.
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Brouillon'
        PENDING = 'pending', 'En attente de paiement'
        PAID = 'paid', 'Payée'
        CONTESTED = 'contested', 'Contestée'

    class PeriodCode(models.TextChoices):
        DAILY = 'daily', 'Journalier'
        WEEKLY = 'weekly', 'Hebdomadaire'
        MONTHLY = 'monthly', 'Mensuel'

    partner = models.ForeignKey(DeliveryPartner, on_delete=models.CASCADE, related_name='invoices')
    reference = models.CharField(max_length=30, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    period_start = models.DateField()
    period_end = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    # Taux effectifs appliqués (figés au moment de l'émission).
    marketplace_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.10'))
    on_demand_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.15'))
    # Montants en FCFA.
    marketplace_deliveries_count = models.PositiveIntegerField(default=0)
    on_demand_deliveries_count = models.PositiveIntegerField(default=0)
    marketplace_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    on_demand_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    collection_fees = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    total_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    # Réconciliation : montant facturable recalculé sur la période vs montant
    # retenu à l'émission ; écart positif = somme due en plus au partenaire.
    recon_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    recon_diff = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    recon_date = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period_end']

    @classmethod
    def next_reference(cls, period_start):
        """Génère une référence INV-YYYYMM-XXXXX par mois de période."""
        prefix = f"INV-{period_start.strftime('%Y%m')}-"
        last = (
            cls.objects.filter(reference__startswith=prefix)
            .order_by("-reference")
            .values_list("reference", flat=True)
            .first()
        )
        sequence = int(last.split("-")[-1]) + 1 if last else 1
        return f"{prefix}{sequence:05d}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self.next_reference(self.period_start)
        super().save(*args, **kwargs)

    @property
    def balance(self):
        return self.total_due - self.collection_fees

    def mark_paid(self, user=None):
        from apps.security.utils import log_security_event

        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        self.save()
        log_security_event(
            "PARTNER_INVOICE_PAID", device=user, metadata={"invoice": self.reference, "amount": str(self.balance)},
        )

    def __str__(self):
        return f"{self.reference} ({self.partner.name})"


class GlobalOrder(models.Model):
    """Commande globale multi-boutiques (spec multi-boutiques §1).

    Un client achète des produits de plusieurs boutiques dans un seul panier
    et ne paie qu'une seule fois (un Payment unique). La commande globale
    regroupe les `Order` (sous-commandes, une par boutique) — chaque vendeur
    ne voit et ne gère que sa propre sous-commande — et porte un montant de
    livraison unique facturé au client (`delivery_fee`), distinct des montants
    produits des sous-commandes.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        CANCELLED = 'cancelled', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=30, unique=True, blank=True, default="")
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='global_orders')
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name='global_orders')
    delivery_type = models.CharField(
        max_length=20, choices=[('pickup', 'pickup'), ('standard', 'standard'), ('express', 'express')],
        default='standard',
    )
    items_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def next_reference(cls):
        today = timezone.localdate()
        prefix = f"SM-{today.strftime('%Y%m%d')}-"
        last = (
            cls.objects.filter(reference__startswith=prefix)
            .order_by("-reference")
            .values_list("reference", flat=True)
            .first()
        )
        sequence = int(last.split("-")[-1]) + 1 if last else 1
        return f"{prefix}{sequence:06d}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self.next_reference()
        super().save(*args, **kwargs)

    @property
    def number_of_stores(self):
        return self.orders.count()

    @property
    def number_of_pickups(self):
        delivery = self.deliveries.first()
        return delivery.pickups.count() if delivery else self.orders.count()

    def __str__(self):
        return f"GlobalOrder {self.reference} ({self.customer.email})"


class DeliveryPickup(models.Model):
    """Un point de collecte d'une mission de livraison. (spec multi-boutiques §7)

    Chaque point est indépendant : la boutique, son adresse/GPS (copie à
    l'instant T), les colis (nombre/poids/volume) et son propre statut de
    collecte. La livraison globale ne progresse qu'à la collecte progressive
    des points requis.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'En attente de collecte'
        READY = 'ready', 'Prêt — le vendeur a préparé le colis'
        PICKED_UP = 'picked_up', 'Colis récupéré'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery = models.ForeignKey(Delivery, on_delete=models.CASCADE, related_name='pickups')
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='delivery_pickups')
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='delivery_pickups'
    )
    # Copie de l'adresse/GPS au moment de la commande (le marchand peut ensuite
    # bouger sa boutique : l'itinéraire historique reste fidèle).
    address = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    package_count = models.PositiveIntegerField(default=1)
    package_weight = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    package_volume = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    pickup_status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    pickup_order = models.PositiveIntegerField(default=1)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ['pickup_order']
        unique_together = [['delivery', 'store']]

    def __str__(self):
        return f"{self.delivery.reference} - {self.store.name} (#{self.pickup_order})"


class DeliveryPricingRule(models.Model):
    """Règles de tarification livraison configurables par l'administration.

    (spec multi-boutiques §7, §8) — les montants ne sont jamais codés en dur
    dans le moteur : tout est lu depuis cette table (placée en singleton actif
    par défaut). Le client paie toujours le tarif calculé ; la marge Sunu Mall
    = tarif facturé − coût partenaire, jamais mélangée aux revenus produits.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, default="Règles par défaut")
    is_active = models.BooleanField(default=True)
    base_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1500'))
    extra_pickup_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('800'))
    per_km_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('150'))
    weight_per_kg_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    volume_per_m3_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    package_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    express_surcharge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('800'))
    min_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1000'))
    max_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def active(cls):
        return cls.objects.filter(is_active=True).first()

    @classmethod
    def get_or_create_default(cls):
        rule = cls.active()
        if rule is None:
            rule = cls.objects.create(name="Règles par défaut", is_active=True)
        return rule

    def __str__(self):
        return f"{self.name} ({self.base_fee} FCFA + {self.extra_pickup_fee}/point + {self.per_km_fee}/km)"
