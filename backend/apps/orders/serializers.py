from rest_framework import serializers
from .models import (
    Address, Delivery, DeliveryEvent, DeliveryPartner, DeliveryTracking,
    DeliveryZone, Driver, Order, OrderItem, PartnerInvoice, PartnerZonePricing,
)


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ["id", "user", "label", "street", "city", "country", "latitude", "longitude", "created_at"]
        read_only_fields = ["id", "user", "created_at"]


class DeliveryZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryZone
        fields = ["id", "name", "boundary_geojson", "created_at"]
        read_only_fields = ["id", "created_at"]


class DriverSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.get_full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    last_position = serializers.SerializerMethodField()
    position_updated_at = serializers.DateTimeField(read_only=True)
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = [
            "id", "user", "full_name", "phone", "email", "zone", "vehicle_type",
            "availability_status", "last_position", "position_updated_at",
            "distance_km", "partner", "is_suspended", "max_active_deliveries",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "user": {"read_only": True},
            "partner": {"required": False, "allow_null": True},
            "is_suspended": {"required": False},
            "max_active_deliveries": {"required": False},
        }

    def get_last_position(self, obj):
        if obj.last_latitude is None or obj.last_longitude is None:
            return None
        return {"latitude": obj.last_latitude, "longitude": obj.last_longitude}

    def get_distance_km(self, obj):
        store = self.context.get("store")
        if store is None:
            return None
        distance = obj.distance_to_store_km(store)
        return round(distance, 2) if distance is not None else None


class DeliveryTrackingSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryTracking
        fields = ["id", "delivery", "latitude", "longitude", "recorded_at"]
        read_only_fields = ["id", "recorded_at"]


class DeliveryEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryEvent
        fields = [
            "id", "action", "actor", "actor_name", "actor_role",
            "previous_status", "new_status", "comment", "metadata", "created_at",
        ]
        read_only_fields = fields

    def get_actor_name(self, obj):
        if not obj.actor:
            return ""
        return obj.actor.get_full_name() or obj.actor.email


class DeliverySerializer(serializers.ModelSerializer):
    driver_detail = DriverSerializer(source="driver", read_only=True)
    partner_detail = serializers.SerializerMethodField()
    last_position = serializers.SerializerMethodField()
    eta_seconds = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()

    class Meta:
        model = Delivery
        fields = [
            "id", "reference", "order", "driver", "driver_detail", "status",
            "partner", "partner_detail", "picked_up_at", "delivered_at",
            "last_position", "eta_seconds", "timeline",
            "proof_method", "proof_note", "proof_photo", "proof_latitude",
            "proof_longitude", "proof_recorded_at",
            "failure_reason", "failure_comment", "return_reason", "refuse_reason",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "reference", "order", "created_at", "updated_at",
            "last_position", "eta_seconds", "timeline",
        ]

    def get_last_position(self, obj):
        tracking = obj.trackings.first()
        if not tracking:
            return None
        return {
            "latitude": tracking.latitude,
            "longitude": tracking.longitude,
            "recorded_at": tracking.recorded_at,
        }

    def get_eta_seconds(self, obj):
        return obj.eta_seconds()

    def get_partner_detail(self, obj):
        if not obj.partner_id:
            return None
        return {
            "id": str(obj.partner_id),
            "name": obj.partner.name,
            "phone": obj.partner.contact_phone,
        }

    def get_timeline(self, obj):
        events = obj.events.values(
            "action", "actor_role", "previous_status", "new_status",
            "comment", "created_at",
        )
        return list(events)


class DeliveryPartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryPartner
        fields = [
            "id", "name", "contact_name", "contact_email", "contact_phone",
            "address", "city", "status", "score",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "score", "created_at", "updated_at"]


class DeliveryPartnerDetailSerializer(DeliveryPartnerSerializer):
    drivers_count = serializers.SerializerMethodField()
    deliveries_count = serializers.SerializerMethodField()
    delivered_count = serializers.SerializerMethodField()
    success_rate = serializers.SerializerMethodField()
    return_rate = serializers.SerializerMethodField()
    active_zones = serializers.SerializerMethodField()

    class Meta(DeliveryPartnerSerializer.Meta):
        fields = [
            "id", "name", "contact_name", "contact_email", "contact_phone",
            "address", "city", "status", "score",
            "drivers_count", "deliveries_count", "delivered_count",
            "success_rate", "return_rate", "active_zones",
            "created_at", "updated_at",
        ]

    def get_drivers_count(self, obj):
        return obj.drivers.count()

    def get_deliveries_count(self, obj):
        return obj.deliveries.count()

    def get_delivered_count(self, obj):
        return obj.deliveries.filter(status=Delivery.Status.DELIVERED).count()

    def get_success_rate(self, obj):
        return obj.success_rate()

    def get_return_rate(self, obj):
        return obj.return_rate()

    def get_active_zones(self, obj):
        return [
            {"id": str(zp.zone_id), "name": zp.zone.name, "client_fee": str(zp.client_fee)}
            for zp in obj.zone_pricings.select_related("zone").filter(is_available=True)
        ]


class PartnerZonePricingSerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(source="zone.name", read_only=True)

    class Meta:
        model = PartnerZonePricing
        fields = [
            "id", "partner", "zone", "zone_name", "client_fee", "partner_cost",
            "estimated_delay_minutes", "max_weight_kg", "is_available", "margin",
        ]
        read_only_fields = ["id", "zone_name", "margin"]
        extra_kwargs = {"partner": {"read_only": True}}


class PartnerInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerInvoice
        fields = [
            "id", "partner", "reference", "status", "period_start", "period_end",
            "due_date", "marketplace_rate", "on_demand_rate",
            "marketplace_deliveries_count", "on_demand_deliveries_count",
            "marketplace_amount", "on_demand_amount", "collection_fees",
            "total_due", "balance", "recon_amount", "recon_diff", "recon_date",
            "paid_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "reference", "status", "marketplace_rate", "on_demand_rate",
            "marketplace_deliveries_count", "on_demand_deliveries_count",
            "marketplace_amount", "on_demand_amount", "collection_fees",
            "total_due", "balance", "recon_amount", "recon_diff", "recon_date",
            "paid_at", "created_at", "updated_at",
        ]
        extra_kwargs = {"partner": {"read_only": True}}


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product_variant.product.name", read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product_variant", "product_name", "quantity", "unit_price"]
        read_only_fields = ["id", "unit_price"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    delivery = DeliverySerializer(read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    address_detail = AddressSerializer(source="address", read_only=True)
    payment = serializers.SerializerMethodField()
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    customer_name = serializers.SerializerMethodField()
    can_be_cancelled = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "customer", "customer_name", "customer_email", "store", "store_name", "address", "address_detail",
            "total_amount", "delivery_fee", "status", "can_be_cancelled", "items", "delivery", "payment",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "customer", "customer_name", "customer_email", "store_name", "address_detail",
            "total_amount", "status", "can_be_cancelled", "items", "delivery", "payment", "created_at", "updated_at",
        ]

    def get_customer_name(self, obj):
        return obj.customer.get_full_name() or obj.customer.email

    def get_can_be_cancelled(self, obj):
        return obj.can_be_cancelled()

    def get_payment(self, obj):
        payment = getattr(obj, "payment", None)
        if not payment:
            return None
        refund = payment.refunds.order_by("-created_at").first()
        refund_data = (
            {"id": refund.id, "status": refund.status, "amount": str(refund.amount), "refunded_at": refund.refunded_at}
            if refund
            else None
        )
        return {"id": payment.id, "method": payment.method, "status": payment.status, "refund": refund_data}


class CheckoutItemInputSerializer(serializers.Serializer):
    """Un article du panier envoyé lors du passage de commande."""
    product_variant = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class CheckoutSerializer(serializers.Serializer):
    """
    Payload attendu par OrderViewSet.checkout : construit en une transaction
    ACID la commande, ses lignes, sa livraison et son paiement en attente,
    à partir du panier validé sur les écrans checkout-address / -delivery / -payment.

    Le frais de livraison n'est jamais pris depuis le client : seul
    `delivery_type` est transmis, le montant est recalculé côté serveur
    (voir `apps.orders.pricing.compute_delivery_fee`).
    """
    store = serializers.UUIDField()
    address = serializers.UUIDField()
    delivery_type = serializers.ChoiceField(choices=["pickup", "standard", "express"], default="standard")
    payment_method = serializers.ChoiceField(choices=["wave", "orange_money", "card"])
    items = CheckoutItemInputSerializer(many=True)


class DeliveryQuoteSerializer(serializers.Serializer):
    """Payload pour prévisualiser le frais de livraison avant de passer commande."""
    store = serializers.UUIDField()
    address = serializers.UUIDField()
    delivery_type = serializers.ChoiceField(choices=["pickup", "standard", "express"], default="standard")
