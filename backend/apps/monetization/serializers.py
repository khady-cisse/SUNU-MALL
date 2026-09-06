from rest_framework import serializers
from .models import (
    Notification, SponsoredProduct, SubscriptionPlan,
    Subscription, Invoice
)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "user", "channel", "subject", "message", "status", "is_read", "sent_at", "created_at"]
        read_only_fields = ["id", "created_at"]


class SponsoredProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = SponsoredProduct
        fields = [
            "id", "product", "store", "daily_budget", 
            "starts_at", "ends_at", "status", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            "id", "name", "price", "billing_cycle", "features", "max_products",
            "commission_rate", "duration_days", "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = [
            "id", "plan", "subscriber_type", "subscriber_id",
            "status", "starts_at", "ends_at", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            "id", "subscription", "amount", "status",
            "issued_at", "due_at", "paid_at", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
