from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    AddressViewSet, DeliveryEventStreamView, DeliveryPricingRuleViewSet,
    DeliveryViewSet, DriverViewSet, GlobalOrderViewSet, OrderViewSet,
    PartnerSpaceViewSet, PartnerViewSet, TrackOrderView,
)

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")
router.register("drivers", DriverViewSet, basename="driver")
router.register("deliveries", DeliveryViewSet, basename="delivery")
router.register("partners", PartnerViewSet, basename="partner")
router.register("global-orders", GlobalOrderViewSet, basename="global-order")
router.register("delivery-pricing-rules", DeliveryPricingRuleViewSet, basename="delivery-pricing-rule")
router.register("", OrderViewSet, basename="order")

urlpatterns = [
    # Suivi de commande invité (sans connexion) — GET /api/orders/track/ (POST)
    path("track/", TrackOrderView.as_view(), name="order-track"),
    *router.urls,
    # Flux temps réel (SSE) — GET /api/orders/deliveries/{id}/events/
    path(
        "deliveries/<uuid:pk>/events/",
        DeliveryEventStreamView.as_view({"get": "get"}),
        name="delivery-events",
    ),
    # Espace Partenaire (rôle `partner`)
    path("partner/profile/", PartnerSpaceViewSet.as_view({"get": "profile", "patch": "profile"}), name="partner-profile"),
    path("partner/api-key/", PartnerSpaceViewSet.as_view({"post": "api_key"}), name="partner-api-key"),
    path("partner/banks/", PartnerSpaceViewSet.as_view({"get": "banks"}), name="partner-banks"),
    path("partner/stats/", PartnerSpaceViewSet.as_view({"get": "stats"}), name="partner-stats"),
    path("partner/deliveries/", PartnerSpaceViewSet.as_view({"get": "deliveries"}), name="partner-deliveries"),
    path("partner/invoices/", PartnerSpaceViewSet.as_view({"get": "invoices"}), name="partner-invoices"),
    path("partner/invoices/<uuid:pk>/", PartnerSpaceViewSet.as_view({"get": "invoice_detail"}), name="partner-invoice-detail"),
    path("partner/zones/", PartnerSpaceViewSet.as_view({"get": "zones"}), name="partner-zones"),
    path("partner/zones/<uuid:pk>/", PartnerSpaceViewSet.as_view({"patch": "zone_update"}), name="partner-zone-update"),
]