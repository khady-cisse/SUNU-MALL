from rest_framework.routers import DefaultRouter
from .views import (
    NotificationViewSet, SubscriptionPlanViewSet, SubscriptionViewSet,
    SubscriptionHistoryViewSet, InvoiceViewSet, SponsoredProductViewSet,
)

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")
# `plans` est l'endpoint contractuel (spec §26) ; `subscription-plans` reste
# en place pour la rétrocompatibilité du frontend existant.
router.register("plans", SubscriptionPlanViewSet, basename="plan")
router.register("subscription-plans", SubscriptionPlanViewSet, basename="subscription-plan")
router.register("subscription", SubscriptionViewSet, basename="subscription")
router.register("subscriptions", SubscriptionViewSet, basename="subscriptions")
router.register("subscription-history", SubscriptionHistoryViewSet, basename="subscription-history")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("sponsored-products", SponsoredProductViewSet, basename="sponsored-product")

urlpatterns = router.urls