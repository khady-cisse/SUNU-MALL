from django.contrib import admin

from .models import BackupRecord, DeploymentVersion, EmergencyAccess, Incident, SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ["key", "label", "value_type", "value", "is_flag", "updated_at"]
    search_fields = ["key", "label"]
    list_filter = ["value_type", "is_flag"]


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ["reference", "title", "severity", "status", "started_at", "updated_at"]
    list_filter = ["severity", "status"]
    search_fields = ["reference", "title"]


@admin.register(DeploymentVersion)
class DeploymentVersionAdmin(admin.ModelAdmin):
    list_display = ["version", "environment", "status", "is_active", "deployed_at"]
    list_filter = ["environment", "status", "is_active"]


@admin.register(BackupRecord)
class BackupRecordAdmin(admin.ModelAdmin):
    list_display = ["reference", "backup_type", "status", "size_bytes", "finished_at"]
    list_filter = ["backup_type", "status"]


@admin.register(EmergencyAccess)
class EmergencyAccessAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "status", "expires_at", "created_at"]
    list_filter = ["status"]
    search_fields = ["title", "user__email"]