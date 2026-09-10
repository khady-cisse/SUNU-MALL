"""Routes de l'administration technique (apps/ops)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("settings", views.SystemSettingViewSet, basename="ops-settings")
router.register("incidents", views.IncidentViewSet, basename="ops-incidents")
router.register("versions", views.DeploymentVersionViewSet, basename="ops-versions")
router.register("backups", views.BackupRecordViewSet, basename="ops-backups")
router.register("emergency", views.EmergencyAccessViewSet, basename="ops-emergency")

urlpatterns = [
    path("alerts/", views.AlertCenterView.as_view(), name="ops-alerts"),
    path("", include(router.urls)),
]