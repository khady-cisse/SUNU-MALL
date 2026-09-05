from rest_framework import serializers
from .models import Address, DeliveryZone, Driver, Delivery, DeliveryTracking, Order, OrderItem


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

    class Meta:
        model = Driver
        fields = [
            "id", "user", "full_name", "phone", "zone", "vehicle_type",
            "availability_status", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class DeliveryTrackingSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryTracking
        fields = ["id", "delivery", "latitude", "longitude", "recorded_at"]
        read_only_fields = ["id", "recorded_at"]


class DeliverySerializer(serializers.ModelSerializer):
    driver_detail = DriverSerializer(source="driver", read_only=True)
    last_position = serializers.SerializerMethodField()
    eta_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Delivery
        fields = [
            "id", "order", "driver", "driver_detail", "status",
            "picked_up_at", "delivered_at", "last_position", "eta_seconds",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "order", "created_at", "updated_at", "last_position", "eta_seconds"]

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
