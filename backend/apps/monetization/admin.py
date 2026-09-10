from datetime import timedelta

from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils import timezone

from apps.security.utils import log_security_event
from .models import (
    Notification, SponsoredProduct, SubscriptionPlan,
    Subscription, SubscriptionHistory, Invoice
)


class SubscriptionHistoryInline(admin.TabularInline):
    """Historique immutable : visible mais jamais modifiable/supprimable."""
    model = SubscriptionHistory
    extra = 0
    can_delete = False
    readonly_fields = ["action", "old_plan", "new_plan", "old_end_date", "new_end_date", "performed_by", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "price", "max_products", "commission_rate", "duration_days", "is_active"]
    list_editable = ["is_active"]
    search_fields = ["code", "name"]


class SubscriptionChangePlanForm(forms.Form):
    new_plan = forms.ModelChoiceField(
        queryset=SubscriptionPlan.objects.filter(is_active=True), label="Nouvelle formule",
    )


def _sync_commission(subscription):
    from apps.commissions.services import sync_plan_from_subscription
    sync_plan_from_subscription(subscription)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["id", "plan_code", "status", "starts_at", "ends_at", "created_at"]
    list_filter = ["status", "plan"]
    search_fields = ["id", "plan__name", "plan__code", "subscriber_id"]
    readonly_fields = ["id", "created_at", "updated_at"]
    inlines = [SubscriptionHistoryInline]
    actions = ["activate_selected", "suspend_selected", "cancel_selected", "change_plan"]

    @admin.display(description="Formule")
    def plan_code(self, obj):
        return obj.plan.code if obj.plan else ""

    def _log(self, request, sub, action, metadata=None):
        log_security_event(
            request.user, f"subscription.{action}", request,
            {"subscription_id": str(sub.id), **(metadata or {})},
        )

    @admin.action(description="Activer (ré) l'abonnement sélectionné")
    def activate_selected(self, request, queryset):
        today = timezone.now().date()
        count = 0
        for sub in queryset:
            sub.status = Subscription.Status.ACTIVE
            sub.starts_at = today
            sub.ends_at = today + timedelta(days=sub.plan.duration_days or 30)
            sub.save()
            sub.record_history(
                SubscriptionHistory.Action.ACTIVATED,
                old_plan=sub.plan, new_plan=sub.plan,
                old_end_date=None, new_end_date=sub.ends_at,
            )
            _sync_commission(sub)
            self._log(request, sub, "activated", {"plan": sub.plan.code})
            count += 1
        self.message_user(request, f"{count} abonnement(s) activé(s).")

    @admin.action(description="Suspendre l'abonnement sélectionné")
    def suspend_selected(self, request, queryset):
        count = 0
        for sub in queryset:
            sub.suspend(performed_by=request.user)
            _sync_commission(sub)
            self._log(request, sub, "suspended", {"plan": sub.plan.code})
            count += 1
        self.message_user(request, f"{count} abonnement(s) suspendu(s).")

    @admin.action(description="Annuler l'abonnement sélectionné")
    def cancel_selected(self, request, queryset):
        count = 0
        for sub in queryset:
            sub.cancel()
            _sync_commission(sub)
            self._log(request, sub, "cancelled", {"plan": sub.plan.code})
            count += 1
        self.message_user(request, f"{count} abonnement(s) annulé(s).")

    @admin.action(description="Changer la formule des abonnements sélectionnés")
    def change_plan(self, request, queryset):
        if "apply" in request.POST:
            form = SubscriptionChangePlanForm(request.POST)
            if form.is_valid():
                new_plan = form.cleaned_data["new_plan"]
                count = 0
                for sub in queryset:
                    sub.change_plan(new_plan)
                    _sync_commission(sub)
                    self._log(request, sub, "plan_changed", {"old": None, "new": new_plan.code})
                    count += 1
                self.message_user(request, f"{count} abonnement(s) passé(s) sur « {new_plan.code} ».")
                return redirect(request.get_full_path())
        form = SubscriptionChangePlanForm()
        return TemplateResponse(
            request, "admin/monetization/change_plan.html",
            {"form": form, "subscriptions": queryset, "title": "Changer la formule", "opts": self.model._meta},
        )


@admin.register(SubscriptionHistory)
class SubscriptionHistoryAdmin(admin.ModelAdmin):
    """Lecture seule : l'historique est immuable."""
    list_display = ["subscription", "action", "old_plan", "new_plan", "created_at"]
    list_filter = ["action"]
    search_fields = ["subscription_id", "seller__email"]
    readonly_fields = [f.name for f in SubscriptionHistory._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Notification)
admin.site.register(SponsoredProduct)
admin.site.register(Invoice)