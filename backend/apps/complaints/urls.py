"""Routes du support client (apps/complaints)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("complaints", views.ComplaintViewSet, basename="complaints")
router.register("tickets", views.SupportTicketViewSet, basename="support-tickets")

urlpatterns = [
    path("", include(router.urls)),
]