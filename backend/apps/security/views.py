"""
Vues de consultation des journaux de sécurité et d'audit admin.
Lecture seule — l'écriture est gérée via utils.log_security_event / log_admin_event.
"""
from rest_framework import viewsets, permissions, serializers
from rest_framework.pagination import PageNumberPagination

from apps.users.permissions import IsAdmin

from .models import SecurityLog, AdminAuditLog


class AuditPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class SecurityLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = SecurityLog
        fields = [
            "id", "user", "user_name", "action", "ip_address",
            "user_agent", "metadata", "created_at",
        ]

    def get_user_name(self, obj):
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email
        return None


class AdminAuditLogSerializer(serializers.ModelSerializer):
    admin_name = serializers.SerializerMethodField()

    class Meta:
        model = AdminAuditLog
        fields = [
            "id", "admin", "admin_name", "action", "object_type", "object_id",
            "summary", "changes", "ip_address", "user_agent", "metadata", "created_at",
        ]

    def get_admin_name(self, obj):
        if obj.admin:
            return f"{obj.admin.first_name} {obj.admin.last_name}".strip() or obj.admin.email
        return None


class SecurityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Journal des actions sensibles (login, KYC, paiement, fraude…)."""
    queryset = SecurityLog.objects.select_related("user").all()
    serializer_class = SecurityLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    pagination_class = AuditPagination

    def get_queryset(self):
        qs = super().get_queryset()
        action = self.request.query_params.get("action")
        user = self.request.query_params.get("user")
        if action:
            qs = qs.filter(action=action)
        if user:
            qs = qs.filter(user_id=user)
        return qs


class AdminAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Journal d'audit des actions administratives."""
    queryset = AdminAuditLog.objects.select_related("admin").all()
    serializer_class = AdminAuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    pagination_class = AuditPagination

    def get_queryset(self):
        qs = super().get_queryset()
        action = self.request.query_params.get("action")
        admin = self.request.query_params.get("admin")
        object_type = self.request.query_params.get("object_type")
        if action:
            qs = qs.filter(action=action)
        if admin:
            qs = qs.filter(admin_id=admin)
        if object_type:
            qs = qs.filter(object_type=object_type)
        return qs
