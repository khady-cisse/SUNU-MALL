"""
Vues KYC.

Règle fondamentale (spec §3, §10, §24) : le propriétaire d'un document est
toujours déterminé côté backend à partir de `request.user` et de SON rôle.
Le frontend ne peut jamais choisir, modifier ni transmettre le propriétaire.

Cycle de vie d'un statut (spec §8) :
  PENDING → SUBMITTED → UNDER_REVIEW → VERIFIED
                     ↘ REJECTED → SUBMITTED (nouveau dossier, motif obligatoire)
  VERIFIED → SUSPENDED → UNDE_REVIEW/VERIFIED (par l'admin)
  SUSPENDED / BLOCKED : plus aucune soumission possible.

Endpoints :
  POST /api/kyc/seller-kyc/submit/          (vendeur, multipart)
  POST /api/kyc/driver-kyc/submit/          (livreur, multipart)
  GET  /api/kyc/seller-kyc/me | /driver-kyc/me   (son propre dossier)
  GET  /api/kyc/seller-kyc/?status=…        (admin — filtrable par statut)
  Listes/recherche/actions admin (approve, reject, request_resubmission,
  start_review, suspend, block) réservées aux admins.
"""
import django.core.exceptions
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.users.models import Role
from apps.users.permissions import IsAdmin
from .models import DriverKYC, SellerKYC, VerificationHistory
from .serializers import (
    DriverKYCSerializer, DriverKYCSubmitSerializer,
    SellerKYCSerializer, SellerKYCSubmitSerializer,
)
from .storage import save_document
from .utils import (
    _document_fingerprint,
    log_kyc_security,
    notify_kyc_approved,
    notify_kyc_blocked,
    notify_kyc_rejected,
    notify_kyc_resubmission,
    notify_kyc_submitted,
    notify_kyc_suspended,
    notify_kyc_under_review,
    notify_kyc_uploaded,
    record_kyc_audit,
)

_STATUS_FIELDS = ["document_type", "document_front", "document_back", "status",
                  "rejection_reason", "submitted_at", "verified_at", "updated_at"]

_SECURITY_ACTION = {
    "submit": "KYC_DOCUMENT_UPLOAD",
    "approve": "KYC_APPROVED",
    "reject": "KYC_REJECTED",
    "resubmit": "KYC_REQUEST_RESUBMISSION",
    "suspend": "KYC_SUSPENDED",
    "block": "KYC_BLOCKED",
}


def _require_reason(data, field="reason"):
    reason = (data or {}).get(field, "").strip()
    if not reason:
        raise ValidationError({field: "Le motif est obligatoire pour cette action."})
    return reason


class _KYCViewSetBase(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Logique commune aux dossiers vendeur et livreur (jamais mélangés)."""

    kyc_model = None
    submit_serializer_class = None
    required_role = None
    owner_type = None  # "seller" | "driver"
    serializer_class = None
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status"]

    def get_queryset(self):
        return self.kyc_model.objects.all()

    def get_permissions(self):
        if self.action in ["list", "retrieve", "approve", "reject",
                           "request_resubmission", "start_review", "suspend", "block"]:
            return [permissions.IsAuthenticated(), IsAdmin()]
        return [permissions.IsAuthenticated()]

    def _enforce_role(self):
        user = self.request.user
        if not user.has_role(self.required_role):
            raise PermissionDenied(
                f"Réservé aux comptes « {self.owner_type} » : votre rôle ne permet pas cette action."
            )
        return user

    def _audit(self, instance, action_verb):
        record_kyc_audit(
            self.request.user,
            instance,
            f"ADMIN_{action_verb}_{self.owner_type.upper()}_KYC",
        )

    def _log_security(self, instance, action_key, metadata=None):
        user = instance.owner()
        log_kyc_security(
            user,
            _SECURITY_ACTION[action_key],
            self.request,
            metadata={
                "kyc_id": str(instance.id),
                "owner_email": user.email,
                **(metadata or {}),
            },
        )

    def _record_history(self, instance, new_status, previous_status, reviewed_by, reason=""):
        """Historique de vérification : uniquement les vendeurs (spec §12 — la
        table historique porte sur le compte vendeur)."""
        if not isinstance(instance, SellerKYC):
            return
        VerificationHistory.record(
            instance, new_status, reviewed_by, reason=reason, previous_status=previous_status
        )

    def _get_coherent(self):
        """
        Récupère le dossier ET vérifie la cohérence propriétaire/rôle.
        Convertit la ValidationError modèle en erreur DRF 400 — sans quoi elle
        remonterait en 500.
        """
        instance = self.get_object()
        try:
            instance.validate_owner_role()
        except django.core.exceptions.ValidationError as exc:
            raise ValidationError({"detail": exc.messages[0] if exc.messages else "Dossier incohérent."})
        return instance

    # --- Upload par l'utilisateur concerné ---

    @action(detail=False, methods=["post"], url_path="submit")
    def submit(self, request):
        user = self._enforce_role()
        serializer = self.submit_serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        kyc, created = self.kyc_model.objects.get_or_create(**{self.owner_type: user})

        if kyc.status in self.kyc_model.NON_SELLING_STATUSES:
            raise ValidationError({
                "detail": "Ce compte ne peut plus soumettre de dossier de vérification. Contactez le support.",
            })

        kyc.document_type = serializer.validated_data["document_type"]
        if isinstance(kyc, SellerKYC) and "address" in serializer.validated_data:
            kyc.address = serializer.validated_data.get("address") or ""
        kyc.document_front = save_document(kyc, "front", serializer.validated_data["document_front"])
        kyc.document_back = save_document(kyc, "back", serializer.validated_data["document_back"])

        if isinstance(kyc, SellerKYC):
            # Empreinte du recto pour détecter un document réutilisé (fraude).
            kyc.document_hash = _document_fingerprint(serializer.validated_data["document_front"])

        previous_status = kyc.status
        kyc.mark_submitted()

        self._record_history(kyc, SellerKYC.Status.SUBMITTED if isinstance(kyc, SellerKYC)
                             else DriverKYC.Status.SUBMITTED,
                             previous_status, user)
        notify_kyc_uploaded(user)
        notify_kyc_submitted(user)
        self._log_security(kyc, "submit")

        return Response(
            self.serializer_class(kyc, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        user = request.user
        kyc = self.kyc_model.objects.filter(**{self.owner_type: user}).first()
        if not kyc:
            raise NotFound("Aucun dossier KYC soumis.")
        return Response(self.serializer_class(kyc, context={"request": request}).data)

    # --- Actions admin ---

    def retrieve(self, request, *args, **kwargs):
        instance = self._get_coherent()
        self._audit(instance, "VIEW")
        return Response(self.serializer_class(instance, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        kyc = self._get_coherent()
        previous_status = kyc.status
        kyc.mark_verified()
        self._record_history(kyc, SellerKYC.Status.VERIFIED, previous_status,
                             request.user, reason=(request.data or {}).get("reason", ""))
        notify_kyc_approved(kyc.owner())
        self._audit(kyc, "APPROVE")
        self._log_security(kyc, "approve")
        return Response(self.serializer_class(kyc, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        kyc = self._get_coherent()
        reason = _require_reason(request.data)
        previous_status = kyc.status
        kyc.mark_rejected(reason)
        self._record_history(kyc, self.kyc_model.Status.REJECTED, previous_status,
                             request.user, reason=reason)
        notify_kyc_rejected(kyc.owner(), reason)
        self._audit(kyc, "REJECT")
        self._log_security(kyc, "reject", {"reason": reason})
        return Response(self.serializer_class(kyc, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="request-resubmission")
    def request_resubmission(self, request, pk=None):
        """Nouvelle soumission demandée : le dossier repasse en REJECTED avec
        un motif OBLIGATOIRE et une notification dédiée (spec §11)."""
        kyc = self._get_coherent()
        reason = _require_reason(request.data)
        previous_status = kyc.status
        kyc.mark_rejected(reason)
        self._record_history(kyc, self.kyc_model.Status.REJECTED, previous_status,
                             request.user, reason=f"[Nouvelle soumission] {reason}")
        notify_kyc_resubmission(kyc.owner(), reason)
        self._audit(kyc, "RESUBMIT")
        self._log_security(kyc, "resubmit", {"reason": reason})
        return Response(self.serializer_class(kyc, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="start-review")
    def start_review(self, request, pk=None):
        """L'admin passe le dossier en cours d'examen (spec §7)."""
        kyc = self._get_coherent()
        previous_status = kyc.status
        kyc.mark_under_review()
        self._record_history(kyc, self.kyc_model.Status.UNDER_REVIEW, previous_status,
                             request.user, reason="")
        notify_kyc_under_review(kyc.owner())
        self._audit(kyc, "REVIEW")
        return Response(self.serializer_class(kyc, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="suspend")
    def suspend(self, request, pk=None):
        """Suspension temporaire : le compte cesse de pouvoir vendre (spec §8)."""
        kyc = self._get_coherent()
        reason = (request.data or {}).get("reason", "").strip()
        previous_status = kyc.status
        kyc.mark_suspended(reason)
        self._record_history(kyc, self.kyc_model.Status.SUSPENDED, previous_status,
                             request.user, reason=reason)
        notify_kyc_suspended(kyc.owner(), reason)
        self._audit(kyc, "SUSPEND")
        self._log_security(kyc, "suspend", {"reason": reason})
        return Response(self.serializer_class(kyc, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="block")
    def block(self, request, pk=None):
        """Blocage définitif : le compte ne peut plus jamais vendre (spec §8)."""
        kyc = self._get_coherent()
        reason = (request.data or {}).get("reason", "").strip()
        previous_status = kyc.status
        kyc.mark_blocked(reason)
        self._record_history(kyc, self.kyc_model.Status.BLOCKED, previous_status,
                             request.user, reason=reason)
        notify_kyc_blocked(kyc.owner(), reason)
        self._audit(kyc, "BLOCK")
        self._log_security(kyc, "block", {"reason": reason})
        return Response(self.serializer_class(kyc, context={"request": request}).data)


class SellerKYCViewSet(_KYCViewSetBase):
    kyc_model = SellerKYC
    submit_serializer_class = SellerKYCSubmitSerializer
    required_role = Role.RoleName.MERCHANT
    owner_type = "seller"
    serializer_class = SellerKYCSerializer


class DriverKYCViewSet(_KYCViewSetBase):
    kyc_model = DriverKYC
    submit_serializer_class = DriverKYCSubmitSerializer
    required_role = Role.RoleName.DRIVER
    owner_type = "driver"
    serializer_class = DriverKYCSerializer