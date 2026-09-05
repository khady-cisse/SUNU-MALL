"""
Vues KYC.

Règle fondamentale (spec §3, §10, §24) : le propriétaire d'un document est
toujours déterminé côté backend à partir de `request.user` et de SON rôle.
Le frontend ne peut jamais choisir, modifier ni transmettre le propriétaire.

Endpoints :
  POST /api/seller-kyc/submit/          (vendeur, multipart)
  POST /api/driver-kyc/submit/          (livreur, multipart)
  GET  /api/seller-kyc/me  et /driver-kyc/me   (son propre dossier)
  Lists/details/approuve/rejette        (admin uniquement)
"""
import django.core.exceptions
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.users.models import Role
from apps.users.permissions import IsAdmin
from .models import DriverKYC, SellerKYC
from .serializers import (
    DriverKYCSerializer, DriverKYCSubmitSerializer,
    SellerKYCSerializer, SellerKYCSubmitSerializer,
)
from .storage import save_document
from .utils import (
    notify_kyc_approved,
    notify_kyc_rejected,
    notify_kyc_uploaded,
    record_kyc_audit,
)

_STATUS_FIELDS = ["document_type", "document_front", "document_back", "status",
                  "rejection_reason", "submitted_at", "verified_at", "updated_at"]


class _KYCViewSetBase(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Logique commune aux dossiers vendeur et livreur (jamais mélangés)."""

    kyc_model = None
    submit_serializer_class = None
    required_role = None
    owner_type = None  # "seller" | "driver"
    serializer_class = None
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return self.kyc_model.objects.all()

    def get_permissions(self):
        if self.action in ["list", "retrieve", "approve", "reject"]:
            return [permissions.IsAuthenticated(), IsAdmin()]
        return [permissions.IsAuthenticated()]

    def _enforce_role(self):
        user = self.request.user
        if not user.has_role(self.required_role):
            raise PermissionDenied(
                f"Réservé aux comptes « {self.owner_type} » : votre rôle ne permet pas cette action."
            )
        return user

    def _audit(self, action_verb):
        record_kyc_audit(
            self.request.user,
            self.get_object(),
            f"ADMIN_{action_verb}_{self.owner_type.upper()}_KYC",
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

        kyc.document_type = serializer.validated_data["document_type"]
        kyc.document_front = save_document(kyc, "front", serializer.validated_data["document_front"])
        kyc.document_back = save_document(kyc, "back", serializer.validated_data["document_back"])
        kyc.status = self.kyc_model.Status.PENDING
        kyc.rejection_reason = None
        kyc.verified_at = None
        kyc.submitted_at = timezone.now()
        kyc.save(update_fields=_STATUS_FIELDS)

        notify_kyc_uploaded(user)
        return Response(
            self.serializer_class(kyc).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        user = request.user
        kyc = self.kyc_model.objects.filter(**{self.owner_type: user}).first()
        if not kyc:
            raise NotFound("Aucun dossier KYC soumis.")
        return Response(self.serializer_class(kyc).data)

    # --- Actions admin ---

    def retrieve(self, request, *args, **kwargs):
        instance = self._get_coherent()
        self._audit("VIEW")
        return Response(self.serializer_class(instance).data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        kyc = self._get_coherent()
        kyc.mark_verified()
        notify_kyc_approved(kyc.owner())
        self._audit("APPROVE")
        return Response(self.serializer_class(kyc).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        kyc = self._get_coherent()
        reason = (request.data or {}).get("reason", "")
        kyc.mark_rejected(reason)
        notify_kyc_rejected(kyc.owner(), reason)
        self._audit("REJECT")
        return Response(self.serializer_class(kyc).data)


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