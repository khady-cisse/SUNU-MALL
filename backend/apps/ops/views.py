"""
Vues de l'administration technique (apps/ops).

Endpoints du centre de contrôle technique : paramètres de plateforme,
incidents, versions déployées, sauvegardes, accès d'urgence et centre
d'alertes. Les contrôles de santé publics (/health*) sont déclarés dans
config/urls.py via `ops_health_views`.
"""
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.security.models import AdminAuditLog
from apps.security.utils import log_admin_event
from apps.users.permissions import HasPermission, IsAdmin

from .models import BackupRecord, DeploymentVersion, EmergencyAccess, Incident, SystemSetting
from .serializers import (
    BackupRecordSerializer, DeploymentVersionSerializer, EmergencyAccessSerializer,
    IncidentSerializer, SystemSettingSerializer,
)
from .services import alert_center, health_overall, run_health_checks


class HasOpsPermission(HasPermission):
    """Exige la permission d'administration technique."""
    required_permission = "ops.manage"


class HasSettingsManagePermission(HasPermission):
    """Exige la modification des paramètres de plateforme."""
    required_permission = "settings.manage"


class HealthView(APIView):
    """Point de contrôle de santé public (aucune permission).

    /health/   : statut agrégé ;
    /health/live/  : liveness — répond 200 tant que le processus tourne ;
    /health/ready/ : readiness — 200 si la base répond, 503 sinon.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    mode = "aggregate"

    def get(self, request):
        checks = run_health_checks()
        summary = health_overall(checks)
        if self.mode == "live":
            return Response({"status": "ok", "checks": checks})
        ready_ok = summary != "down"
        data = {"status": summary, "checks": checks, "generated_at": timezone.now()}
        return Response(data, status=status.HTTP_200_OK if ready_ok else status.HTTP_503_SERVICE_UNAVAILABLE)


class SystemSettingViewSet(viewsets.ReadOnlyModelViewSet):
    """Paramètres de plateforme (lecture admin courant, écriture settings.manage)."""
    queryset = SystemSetting.objects.all()
    serializer_class = SystemSettingSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    @action(detail=False, methods=["post"])
    def set(self, request):
        """Met à jour un réglage identifié par sa clé (feature flag, seuil, message)."""
        permission = HasSettingsManagePermission()
        if not permission.has_permission(request, self):
            self.permission_denied(request, message="Permission 'settings.manage' requise.")

        key = request.data.get("key")
        if not key:
            raise PermissionDenied("Champ 'key' requis.")
        setting, _ = SystemSetting.objects.get_or_create(key=key)
        setting.set_value(request.data.get("value"), updated_by=request.user)
        if "label" in request.data:
            setting.label = request.data["label"]
            setting.save(update_fields=["label"])
        log_admin_event(
            request.user, AdminAuditLog.ActionKind.SETTINGS, request,
            object_type="SystemSetting", object_id=key,
            summary=f"Réglage modifié : {key}",
            changes={"value": setting.value},
        )
        return Response(SystemSettingSerializer(setting).data)


class IncidentViewSet(viewsets.ModelViewSet):
    """Incidents techniques : lecture admin, gestion réservée aux ops."""
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy",
                           "resolve", "close", "reopen"]:
            return [permissions.IsAuthenticated(), HasOpsPermission()]
        return [permissions.IsAuthenticated(), IsAdmin()]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        log_admin_event(
            self.request.user, AdminAuditLog.ActionKind.CREATE, self.request,
            object_type="Incident", object_id=instance.reference,
            summary=f"Incident ouvert : {instance.title}",
            changes={"severity": instance.severity},
        )

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        incident = self.get_object()
        incident.resolve(request.data.get("resolution_notes", ""), user=request.user)
        log_admin_event(request.user, AdminAuditLog.ActionKind.RESOLVE, request,
                        object_type="Incident", object_id=incident.reference,
                        summary="Incident résolu")
        return Response(self.get_serializer(incident).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        incident = self.get_object()
        incident.close(user=request.user)
        log_admin_event(request.user, AdminAuditLog.ActionKind.RESOLVE, request,
                        object_type="Incident", object_id=incident.reference,
                        summary="Incident clos")
        return Response(self.get_serializer(incident).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        incident = self.get_object()
        incident.reopen()
        log_admin_event(request.user, AdminAuditLog.ActionKind.UPDATE, request,
                        object_type="Incident", object_id=incident.reference,
                        summary="Incident rouvert")
        return Response(self.get_serializer(incident).data)


class DeploymentVersionViewSet(viewsets.ModelViewSet):
    """Historique des versions déployées + activation (rollback)."""
    queryset = DeploymentVersion.objects.all()
    serializer_class = DeploymentVersionSerializer

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy", "activate"]:
            return [permissions.IsAuthenticated(), HasOpsPermission()]
        return [permissions.IsAuthenticated(), IsAdmin()]

    def perform_create(self, serializer):
        instance = serializer.save(deployed_by=self.request.user)
        if self.request.data.get("activate"):
            instance.mark_active()
        log_admin_event(self.request.user, AdminAuditLog.ActionKind.CREATE, self.request,
                        object_type="DeploymentVersion", object_id=instance.version,
                        summary=f"Déploiement enregistré : {instance.version}")

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        """Marque cette version comme active (rollback vers une version précédente)."""
        version = self.get_object()
        version.mark_active()
        log_admin_event(request.user, AdminAuditLog.ActionKind.UPDATE, request,
                        object_type="DeploymentVersion", object_id=version.version,
                        summary=f"Version activée : {version.version}", changes={"rollback": True})
        return Response(self.get_serializer(version).data)


class BackupRecordViewSet(viewsets.ModelViewSet):
    """Sauvegardes : suivi des tentatives (auto/manuelles) et de leur résultat."""
    queryset = BackupRecord.objects.all()
    serializer_class = BackupRecordSerializer

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy",
                           "mark_success", "mark_failed"]:
            return [permissions.IsAuthenticated(), HasOpsPermission()]
        return [permissions.IsAuthenticated(), IsAdmin()]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user, started_at=timezone.now())
        log_admin_event(self.request.user, AdminAuditLog.ActionKind.CREATE, self.request,
                        object_type="BackupRecord", object_id=instance.reference,
                        summary=f"Sauvegarde demandée : {instance.reference}")

    @action(detail=True, methods=["post"], url_path="mark-success")
    def mark_success(self, request, pk=None):
        record = self.get_object()
        record.mark_success(
            size_bytes=request.data.get("size_bytes"),
            location=request.data.get("location", ""),
        )
        return Response(self.get_serializer(record).data)

    @action(detail=True, methods=["post"], url_path="mark-failed")
    def mark_failed(self, request, pk=None):
        record = self.get_object()
        record.mark_failed(request.data.get("error", "Échec de la sauvegarde"))
        return Response(self.get_serializer(record).data)


class EmergencyAccessViewSet(viewsets.ModelViewSet):
    """Accès d'urgence break-the-glass : ouvert, listé, révoqué."""
    queryset = EmergencyAccess.objects.all()
    serializer_class = EmergencyAccessSerializer

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy", "revoke"]:
            return [permissions.IsAuthenticated(), HasOpsPermission()]
        return [permissions.IsAuthenticated(), IsAdmin()]

    def perform_create(self, serializer):
        instance = serializer.save(
            user=self.request.user,
            ip_address=self.request.META.get("REMOTE_ADDR"),
            user_agent=self.request.META.get("HTTP_USER_AGENT", ""),
        )
        log_admin_event(self.request.user, AdminAuditLog.ActionKind.EMERGENCY, self.request,
                        object_type="EmergencyAccess", object_id=str(instance.id),
                        summary=f"Accès d'urgence ouvert : {instance.title}",
                        changes={"scopes": instance.scopes})

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        access = self.get_object()
        access.revoke()
        log_admin_event(request.user, AdminAuditLog.ActionKind.EMERGENCY, self.request,
                        object_type="EmergencyAccess", object_id=str(access.id),
                        summary="Accès d'urgence révoqué")
        return Response(self.get_serializer(access).data)


class AlertCenterView(APIView):
    """Centre d'alertes du centre de contrôle (agrégats transverses)."""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request):
        return Response({
            "alerts": alert_center(),
            "generated_at": timezone.now(),
        })