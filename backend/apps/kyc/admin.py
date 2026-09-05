from django.contrib import admin
from .models import DriverKYC, KYCAuditLog, SellerKYC


@admin.register(SellerKYC)
class SellerKYCAdmin(admin.ModelAdmin):
    list_display = ("id", "seller", "status", "document_type", "submitted_at", "verified_at")
    list_filter = ("status", "document_type")
    readonly_fields = ("id", "seller", "document_front", "document_back", "created_at", "updated_at")


@admin.register(DriverKYC)
class DriverKYCAdmin(admin.ModelAdmin):
    list_display = ("id", "driver", "status", "document_type", "submitted_at", "verified_at")
    list_filter = ("status", "document_type")
    readonly_fields = ("id", "driver", "document_front", "document_back", "created_at", "updated_at")


@admin.register(KYCAuditLog)
class KYCAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "owner_type", "owner_id", "admin", "created_at")
    list_filter = ("action", "owner_type")
    readonly_fields = ("admin", "kyc_id", "owner_id", "owner_type", "action", "created_at")