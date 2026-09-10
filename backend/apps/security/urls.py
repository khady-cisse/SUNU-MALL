from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import SecurityLogViewSet, AdminAuditLogViewSet

router = DefaultRouter()
router.register("logs", SecurityLogViewSet, basename="security-log")
router.register("audit-logs", AdminAuditLogViewSet, basename="admin-audit-log")

urlpatterns = [
    path("", include(router.urls)),
]
