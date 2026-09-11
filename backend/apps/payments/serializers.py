from rest_framework import serializers
from .models import Payment, Refund


class PaymentSerializer(serializers.ModelSerializer):
    refund = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ["id", "order", "global_order", "subscription", "method", "amount", "status", "provider_ref", "refund", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_refund(self, obj):
        refund = obj.refunds.order_by("-created_at").first()
        if not refund:
            return None
        return {
            "id": refund.id,
            "status": refund.status,
            "amount": str(refund.amount),
            "refunded_at": refund.refunded_at,
        }


class RefundSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source="payment.order_id", read_only=True)
    store_name = serializers.CharField(source="payment.order.store.name", read_only=True)
    customer_email = serializers.EmailField(source="payment.order.customer.email", read_only=True)

    class Meta:
        model = Refund
        fields = [
            "id", "payment", "order_id", "store_name", "customer_email",
            "amount", "reason", "status", "refunded_at", "created_at",
        ]
        read_only_fields = fields
