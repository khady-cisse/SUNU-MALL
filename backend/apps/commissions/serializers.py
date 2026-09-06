from rest_framework import serializers

from .models import CommissionTransaction, Payout, SellerWallet, WalletTransaction


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerWallet
        fields = [
            "seller", "available_balance", "pending_balance",
            "total_earned", "total_withdrawn",
        ]
        read_only_fields = fields


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = [
            "id", "type", "amount", "available_before", "available_after",
            "pending_before", "pending_after", "reference", "order", "description", "created_at",
        ]
        read_only_fields = fields


class CommissionTransactionSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source="order.store.name", read_only=True)
    order_number = serializers.CharField(source="order.id", read_only=True)
    customer_email = serializers.EmailField(source="order.customer.email", read_only=True)

    class Meta:
        model = CommissionTransaction
        fields = [
            "id", "order", "order_number", "store_name", "customer_email", "seller",
            "plan", "gross_amount", "commission_rate", "commission_amount",
            "seller_amount", "is_refunded", "is_released", "created_at", "refunded_at", "released_at",
        ]
        read_only_fields = fields


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = [
            "id", "seller", "amount", "method", "status",
            "reference", "completed_at", "created_at",
        ]
        read_only_fields = ["id", "seller", "status", "reference", "completed_at", "created_at"]