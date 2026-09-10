"""Serialiseurs de l'administration technique (apps/ops)."""
from rest_framework import serializers

from .models import BackupRecord, DeploymentVersion, EmergencyAccess, Incident, SystemSetting


class SystemSettingSerializer(serializers.ModelSerializer):
    value = serializers.JSONField(required=False, allow_null=True)
    typed_value = serializers.SerializerMethodField()

    class Meta:
        model = SystemSetting
        fields = [
            "id", "key", "label", "description", "value_type", "value",
            "typed_value", "is_flag", "updated_at",
        ]
        read_only_fields = ["id", "typed_value", "updated_at"]

    def get_typed_value(self, obj):
        return obj.typed_value()


class IncidentSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = [
            "id", "reference", "title", "description", "severity", "status",
            "resolution_notes", "started_at", "resolved_at", "created_by_name",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "reference", "resolved_at", "created_by_name", "created_at", "updated_at"]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else ""


class DeploymentVersionSerializer(serializers.ModelSerializer):
    deployed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DeploymentVersion
        fields = [
            "id", "version", "commit_sha", "environment", "status", "is_active",
            "notes", "deployed_by_name", "deployed_at",
        ]
        read_only_fields = ["id", "status", "is_active", "deployed_by_name", "deployed_at"]

    def get_deployed_by_name(self, obj):
        return obj.deployed_by.get_full_name() if obj.deployed_by else ""


class BackupRecordSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = BackupRecord
        fields = [
            "id", "reference", "backup_type", "status", "size_bytes", "location",
            "error", "started_at", "finished_at", "created_by_name", "created_at",
        ]
        read_only_fields = ["id", "reference", "status", "finished_at", "created_by_name", "created_at"]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else ""


class EmergencyAccessSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    active = serializers.SerializerMethodField()

    class Meta:
        model = EmergencyAccess
        fields = [
            "id", "user", "user_name", "title", "reason", "scopes", "status",
            "active", "expires_at", "ip_address", "user_agent", "created_at",
        ]
        read_only_fields = ["id", "user", "user_name", "active", "status", "ip_address", "user_agent", "created_at"]

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email

    def get_active(self, obj):
        return obj.is_active()