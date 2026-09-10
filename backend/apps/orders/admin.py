from django.contrib import admin
from .models import (
    DeliveryZone, Driver, Delivery, DeliveryTracking, DeliveryEvent,
    DeliveryPartner, PartnerZonePricing, PartnerInvoice,
    Address, Order, OrderItem, OrderHistory
)


@admin.register(DeliveryPartner)
class DeliveryPartnerAdmin(admin.ModelAdmin):
    list_display = ["name", "contact_name", "contact_phone", "status", "score", "created_at"]
    list_filter = ["status", "city"]
    search_fields = ["name", "contact_name", "contact_email", "contact_phone"]
    readonly_fields = ["score", "api_key_hash", "api_key_last4"]
    actions = ["activate", "suspend"]

    @admin.action(description="Activer les partenaires sélectionnés")
    def activate(self, request, queryset):
        queryset.update(status=DeliveryPartner.Status.ACTIVE)

    @admin.action(description="Suspendre les partenaires sélectionnés")
    def suspend(self, request, queryset):
        queryset.update(status=DeliveryPartner.Status.SUSPENDED)


@admin.register(PartnerZonePricing)
class PartnerZonePricingAdmin(admin.ModelAdmin):
    list_display = ["partner", "zone", "client_fee", "partner_cost", "estimated_delay_minutes", "is_available"]
    list_filter = ["is_available", "partner"]
    autocomplete_fields = ["partner"]


@admin.register(PartnerInvoice)
class PartnerInvoiceAdmin(admin.ModelAdmin):
    list_display = ["reference", "partner", "status", "period_start", "period_end", "total_due", "collection_fees", "paid_at"]
    list_filter = ["status"]
    search_fields = ["reference", "partner__name"]
    readonly_fields = ["reference", "marketplace_amount", "on_demand_amount", "collection_fees", "total_due", "balance", "recon_amount", "recon_diff", "recon_date"]


@admin.register(DeliveryEvent)
class DeliveryEventAdmin(admin.ModelAdmin):
    list_display = ["delivery", "action", "actor_role", "previous_status", "new_status", "created_at"]
    list_filter = ["action", "actor_role"]
    search_fields = ["delivery__reference"]
    readonly_fields = [f.name for f in DeliveryEvent._meta.fields]


admin.site.register(DeliveryZone)
admin.site.register(Driver)
admin.site.register(Delivery)
admin.site.register(DeliveryTracking)
admin.site.register(Address)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(OrderHistory)