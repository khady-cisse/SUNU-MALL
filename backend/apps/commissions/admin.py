from django.contrib import admin

from .models import (
    CommissionTransaction,
    Payout,
    PlatformTransaction,
    PlatformWallet,
    SellerSubscription,
    SellerWallet,
    WalletTransaction,
)


class WalletTransactionInline(admin.TabularInline):
    model = WalletTransaction
    extra = 0
    readonly_fields = [
        "type", "amount", "available_before", "available_after",
        "pending_before", "pending_after", "reference", "order", "created_at",
    ]


@admin.register(SellerSubscription)
class SellerSubscriptionAdmin(admin.ModelAdmin):
    list_display = ["seller", "plan", "status", "trial_ends_at", "starts_at", "ends_at", "updated_at"]
    list_filter = ["status", "plan"]
    search_fields = ["seller__email", "seller__username"]


@admin.register(SellerWallet)
class SellerWalletAdmin(admin.ModelAdmin):
    list_display = ["seller", "available_balance", "pending_balance", "total_earned", "total_withdrawn"]
    search_fields = ["seller__email"]
    inlines = [WalletTransactionInline]


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ["id", "wallet", "type", "amount", "available_after", "pending_after", "reference", "created_at"]
    list_filter = ["type"]


@admin.register(CommissionTransaction)
class CommissionTransactionAdmin(admin.ModelAdmin):
    list_display = [
        "order", "seller", "plan", "gross_amount", "commission_rate",
        "commission_amount", "seller_amount", "is_refunded", "is_released", "created_at",
    ]
    list_filter = ["plan", "is_refunded", "is_released"]
    search_fields = ["seller__email", "order__id"]


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ["id", "seller", "amount", "method", "status", "reference", "created_at"]
    list_filter = ["status"]


@admin.register(PlatformWallet)
class PlatformWalletAdmin(admin.ModelAdmin):
    list_display = [
        "balance", "total_commissions", "total_subscriptions", "total_refunds", "total_payouts",
    ]


@admin.register(PlatformTransaction)
class PlatformTransactionAdmin(admin.ModelAdmin):
    list_display = ["id", "type", "amount", "reference", "order", "created_at"]
    list_filter = ["type"]
    search_fields = ["reference"]