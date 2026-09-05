from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import AddressViewSet, DeliveryEventStreamView, DeliveryViewSet, DriverViewSet, OrderViewSet

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")
router.register("drivers", DriverViewSet, basename="driver")
router.register("deliveries", DeliveryViewSet, basename="delivery")
router.register("", OrderViewSet, basename="order")

urlpatterns = [
    *router.urls,
    # Flux temps réel (SSE) — GET /api/orders/deliveries/{id}/events/
    path(
        "deliveries/<uuid:pk>/events/",
        DeliveryEventStreamView.as_view({"get": "get"}),
        name="delivery-events",
    ),
]
