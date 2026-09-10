from rest_framework import serializers
from .models import (
    Notification, SponsoredProduct, SubscriptionPlan,
    Subscription, SubscriptionHistory, Invoice
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
            "id", "code", "name", "price", "billing_cycle", "features", "max_products",
            "commission_rate", "duration_days", "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_code = serializers.CharField(source="plan.code", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id", "reference", "plan", "plan_code", "plan_name", "subscriber_type", "subscriber_id",
            "status", "starts_at", "ends_at", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class SubscriptionHistorySerializer(serializers.ModelSerializer):
    old_plan_name = serializers.CharField(source="old_plan.name", read_only=True, default=None)
    new_plan_name = serializers.CharField(source="new_plan.name", read_only=True, default=None)

    class Meta:
        model = SubscriptionHistory
        fields = [
            "id", "subscription", "action", "old_plan_name", "new_plan_name",
            "old_end_date", "new_end_date", "performed_by", "metadata", "created_at",
        ]
        read_only_fields = fields


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            "id", "subscription", "amount", "status",
            "issued_at", "due_at", "paid_at", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]