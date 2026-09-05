"""
Modèles KYC : un dossier PAR rôle, jamais un dossier indistinct.

Règle de sécurité absolue : un SellerKYC appartient uniquement à un vendeur
(rôle CA commerçant), un DriverKYC uniquement à un livreur. Le propriétaire est
toujours fixé côté backend à partir du compte authentifié — aucun champ du
frontend ne peut le choisir ou le modifier.
"""
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from apps.users.models import User, Role


class KYCDocument(models.Model):
    """Champs communs aux deux dossiers. Classe abstraite : chaque rôle a SA table."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_type = models.CharField(max_length=30)
    document_front = models.CharField(max_length=500)
    document_back = models.CharField(max_length=500)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.owner_type} KYC {self.id} ({self.get_status_display()})"

    def owner(self):
        raise NotImplementedError

    @property
    def owner_type(self):
        raise NotImplementedError

    def folder_key(self):
        """Dossier MinIO du dossier : `kyc/{rôle}/{owner}/dossier_uuid/`."""
        return f"kyc/{self.owner_type}s/{self.folder_owner_stem()}/{self.id}/"

    def folder_owner_stem(self):
        raise NotImplementedError

    def validate_owner_role(self):
        """
        Vérification de cohérence avant toute action admin : le propriétaire
        doit avoir le rôle correspondant au type de dossier. Impossible de
        "déplacer" une pièce d'un vendeur vers un livreur ou inversement :
        la clé étrangère est typée par rôle, et le rôle est re-situé ici.
        """
        owner = self.owner()
        expected = Role.RoleName.MERCHANT if self.owner_type == "seller" else Role.RoleName.DRIVER
        if not owner.has_role(expected):
            raise ValidationError(
                f"KYC {self.owner_type} invalide : le propriétaire n'a pas le rôle attendu ({expected})."
            )

    def mark_verified(self):
        self.status = self.Status.VERIFIED
        self.verified_at = timezone.now()
        self.rejection_reason = None
        self.save(update_fields=["status", "verified_at", "rejection_reason", "updated_at"])

    def mark_rejected(self, reason=""):
        self.status = self.Status.REJECTED
        self.verified_at = None
        self.rejection_reason = reason or ""
        self.save(update_fields=["status", "verified_at", "rejection_reason", "updated_at"])

    @property
    def is_verified(self):
        return self.status == self.Status.VERIFIED


class SellerKYC(KYCDocument):
    seller = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="seller_kyc",
    )

    def owner(self):
        return self.seller

    @property
    def owner_type(self):
        return "seller"

    def folder_owner_stem(self):
        return f"seller_{self.seller_id}"


class DriverKYC(KYCDocument):
    driver = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="driver_kyc",
    )

    def owner(self):
        return self.driver

    @property
    def owner_type(self):
        return "driver"

    def folder_owner_stem(self):
        return f"driver_{self.driver_id}"


class KYCAuditLog(models.Model):
    """Trace des actions administratives importantes sur les dossiers KYC.

    Jamais les images dans les logs — seulement des identifiants.
    """

    class Action(models.TextChoices):
        ADMIN_VIEW_SELLER_KYC = "ADMIN_VIEW_SELLER_KYC", "ADMIN_VIEW_SELLER_KYC"
        ADMIN_VIEW_DRIVER_KYC = "ADMIN_VIEW_DRIVER_KYC", "ADMIN_VIEW_DRIVER_KYC"
        ADMIN_APPROVE_SELLER_KYC = "ADMIN_APPROVE_SELLER_KYC", "ADMIN_APPROVE_SELLER_KYC"
        ADMIN_APPROVE_DRIVER_KYC = "ADMIN_APPROVE_DRIVER_KYC", "ADMIN_APPROVE_DRIVER_KYC"
        ADMIN_REJECT_SELLER_KYC = "ADMIN_REJECT_SELLER_KYC", "ADMIN_REJECT_SELLER_KYC"
        ADMIN_REJECT_DRIVER_KYC = "ADMIN_REJECT_DRIVER_KYC", "ADMIN_REJECT_DRIVER_KYC"

    admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="kyc_admin_actions")
    kyc_id = models.CharField(max_length=64)
    owner_id = models.CharField(max_length=64)
    owner_type = models.CharField(max_length=16)
    action = models.CharField(max_length=50, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} {self.owner_type}#{self.owner_id} par {self.admin_id}"