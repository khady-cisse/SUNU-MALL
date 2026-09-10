"""
Journal de sécurité SUNU MALL (spec §16).

Toutes les actions sensibles qui touchent un compte sont tracées : connexion,
déconnexion, dépôt de document d'identité, validation/refus admin, suspension,
blocage, retrait d'argent, changement de mot de passe... Les journaux ne
contiennent jamais de données sensibles elles-mêmes (pas d'images, pas de
numéros de documents) : uniquement des identifiants, l'IP, le user-agent et
du contexte métier dans `metadata`.
"""
from django.db import models

from apps.users.models import User


class SecurityLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = "LOGIN", "Connexion"
        LOGOUT = "LOGOUT", "Déconnexion"
        PASSWORD_CHANGE = "PASSWORD_CHANGE", "Changement de mot de passe"
        PHONE_CHANGE = "PHONE_CHANGE", "Changement de numéro de téléphone"
        PAYMENT_INFO_CHANGE = "PAYMENT_INFO_CHANGE", "Changement d'information de paiement"
        KYC_DOCUMENT_UPLOAD = "KYC_DOCUMENT_UPLOAD", "Dépôt de document d'identité"
        KYC_APPROVED = "KYC_APPROVED", "Dossier d'identité validé"
        KYC_REJECTED = "KYC_REJECTED", "Dossier d'identité refusé"
        KYC_REQUEST_RESUBMISSION = "KYC_REQUEST_RESUBMISSION", "Nouvelle soumission demandée"
        KYC_SUSPENDED = "KYC_SUSPENDED", "Compte vendeur suspendu"
        KYC_BLOCKED = "KYC_BLOCKED", "Compte vendeur bloqué"
        PAYOUT_REQUEST = "PAYOUT_REQUEST", "Demande de retrait d'argent"
        FRAUD_FLAG = "FRAUD_FLAG", "Signalement de fraude probable"

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="security_logs",
    )
    action = models.CharField(max_length=50, choices=Action.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Journal de sécurité"
        verbose_name_plural = "Journal de sécurité"

    def __str__(self):
        return f"{self.get_action_display()} — user {self.user_id} @ {self.created_at:%Y-%m-%d %H:%M}"


class AdminAuditLog(models.Model):
    """Journal d'audit des actions administratives (spec §45, §64).

    Trace toute action réalisée depuis les écrans du centre de contrôle :
    qui (admin), quoi (action), sur quoi (type + identifiant d'objet) et avec
    quelles modifications. Comme SecurityLog, ne contient jamais de données
    sensibles — uniquement des identifiants et du contexte métier.
    """
    class ActionKind(models.TextChoices):
        CREATE = "create", "Création"
        UPDATE = "update", "Modification"
        DELETE = "delete", "Suppression"
        APPROVE = "approve", "Approbation"
        REJECT = "reject", "Rejet"
        SUSPEND = "suspend", "Suspension"
        BLOCK = "block", "Blocage"
        RESOLVE = "resolve", "Résolution"
        REFUND = "refund", "Remboursement"
        ASSIGN = "assign", "Assignation"
        EMERGENCY = "emergency", "Accès d'urgence"
        SETTINGS = "settings", "Paramètres"
        OTHER = "other", "Autre"

    id = models.AutoField(primary_key=True)
    admin = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_audit_logs",
    )
    action = models.CharField(max_length=30, choices=ActionKind.choices, default=ActionKind.OTHER)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=200, blank=True)
    summary = models.CharField(max_length=500, blank=True)
    changes = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Journal d'audit admin"
        verbose_name_plural = "Journal d'audit admin"

    def __str__(self):
        return f"{self.get_action_display()} {self.object_type} {self.object_id} — {self.admin_id} @ {self.created_at:%Y-%m-%d %H:%M}"