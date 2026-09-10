"""
Modèles de l'administration technique : paramètres de plateforme (dont
feature flags et mode maintenance), incidents, versions déployées,
sauvegardes et accès d'urgence (break-the-glass).

Ces données alimentent les écrans techniques du centre de contrôle
(monitoring, incidents, déploiements, sauvegardes, restauration).
Les références suivent le format <PREFIXE>-YYYYMMDD-NNNNNN et sont
générées côté serveur, jamais fournies par le client.
"""
from django.db import models
from django.utils import timezone

from apps.users.models import User


def next_daily_reference(qs, prefix):
    """Génère une référence du jour : <PREFIXE>-YYYYMMDD-NNNNNN."""
    today = timezone.now().strftime("%Y%m%d")
    count_so_far = qs.filter(reference__startswith=f"{prefix}-{today}").count()
    return f"{prefix}-{today}-{count_so_far + 1:06d}"


class SystemSetting(models.Model):
    """Paramètre de plateforme stocké en JSON (valeur typée à l'écriture).

    Sert à la fois de store de configuration (délais, seuils) et de store de
    feature flags / mode maintenance interrogé par le reste du projet via
    `apps.ops.services.feature_flag()` et `apps.ops.services.maintenance_mode()`.
    """
    class ValueType(models.TextChoices):
        JSON = "json", "JSON"
        BOOLEAN = "boolean", "Booléen"
        INTEGER = "integer", "Entier"
        STRING = "string", "Texte"

    key = models.CharField(max_length=100, unique=True)
    label = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    value_type = models.CharField(max_length=20, choices=ValueType.choices, default=ValueType.JSON)
    value = models.JSONField(default=None, null=True, blank=True)
    is_flag = models.BooleanField(default=False, help_text="Feature flag affiché comme toggle dans l'UI")
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]
        verbose_name = "Paramètre de plateforme"
        verbose_name_plural = "Paramètres de plateforme"

    def __str__(self):
        return f"{self.key} = {self.value!r}"

    def typed_value(self):
        """Valeur convertie selon son type (cast tolérant aux erreurs)."""
        if self.value is None:
            return None
        if self.value_type == self.ValueType.BOOLEAN:
            return bool(self.value)
        if self.value_type == self.ValueType.INTEGER:
            try:
                return int(self.value)
            except (TypeError, ValueError):
                return None
        return self.value

    def set_value(self, raw, *, updated_by=None):
        """Écrit la valeur après cast selon le type déclaré."""
        if self.value_type == self.ValueType.INTEGER:
            self.value = int(raw)
        elif self.value_type == self.ValueType.BOOLEAN:
            self.value = bool(raw)
        else:
            self.value = raw
        self.updated_by = updated_by
        self.save(update_fields=["value", "updated_by", "updated_at"])


class Incident(models.Model):
    """Incident d'infrastructure ou métier (dégradation signalée V1).

    Le statut suit un cycle de vie explicite : ouvert → en cours
    d'analyse / identifié / atténuation → résolu → clos.
    """
    class Severity(models.TextChoices):
        CRITICAL = "critical", "Critique"
        MAJOR = "major", "Majeur"
        MINOR = "minor", "Mineur"
        INFO = "info", "Informatif"

    class Status(models.TextChoices):
        OPEN = "open", "Ouvert"
        INVESTIGATING = "investigating", "En cours d'analyse"
        IDENTIFIED = "identified", "Cause identifiée"
        MITIGATING = "mitigating", "Atténuation en cours"
        RESOLVED = "resolved", "Résolu"
        CLOSED = "closed", "Clos"

    reference = models.CharField(max_length=40, unique=True, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.INFO)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    resolution_notes = models.TextField(blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="incidents_created")
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="incidents_closed")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Incident"
        verbose_name_plural = "Incidents"

    def __str__(self):
        return f"{self.reference} — {self.title}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = next_daily_reference(Incident.objects.all(), "INC")
        super().save(*args, **kwargs)

    def resolve(self, notes, *, user=None):
        self.status = self.Status.RESOLVED
        self.resolution_notes = notes
        self.resolved_at = timezone.now()
        self.closed_by = user
        self.save(update_fields=["status", "resolution_notes", "resolved_at", "closed_by", "updated_at"])

    def close(self, *, user=None):
        self.status = self.Status.CLOSED
        if not self.resolved_at:
            self.resolved_at = timezone.now()
        self.closed_by = user
        self.save(update_fields=["status", "resolved_at", "closed_by", "updated_at"])

    def reopen(self):
        self.status = self.Status.OPEN
        self.resolved_at = None
        self.save(update_fields=["status", "resolved_at", "updated_at"])


class DeploymentVersion(models.Model):
    """Version déployée du backend (historique des déploiements).

    Permet le suivi des versions et le rollback : `is_active` désigne la
    version courante ; passer un autre enregistrement à actif simule un
    rollback (le déploiement lui-même relève de l'orchestrateur).
    """
    class Status(models.TextChoices):
        DEPLOYING = "deploying", "Déploiement en cours"
        DEPLOYED = "deployed", "Déployé"
        ACTIVE = "active", "Actif (courant)"
        ROLLED_BACK = "rolled_back", "Restauré (rollback)"
        FAILED = "failed", "Échec"

    version = models.CharField(max_length=100, db_index=True)
    commit_sha = models.CharField(max_length=64, blank=True)
    environment = models.CharField(max_length=50, default="production")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DEPLOYED)
    is_active = models.BooleanField(default=False, help_text="Version actuellement en production")
    notes = models.TextField(blank=True)
    deployed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    deployed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-deployed_at"]
        verbose_name = "Version déployée"
        verbose_name_plural = "Versions déployées"

    def __str__(self):
        return f"{self.version} ({self.environment})"

    def mark_active(self):
        DeploymentVersion.objects.filter(environment=self.environment).update(is_active=False)
        self.is_active = True
        self.status = self.Status.ACTIVE
        self.save(update_fields=["is_active", "status", "deployed_at"])


class BackupRecord(models.Model):
    """Journal des sauvegardes (base et/ou fichiers) — automatisées ou manuelles."""
    class BackupType(models.TextChoices):
        DATABASE = "database", "Base de données"
        FILES = "files", "Fichiers / documents"
        FULL = "full", "Sauvegarde complète"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        IN_PROGRESS = "in_progress", "En cours"
        SUCCESS = "success", "Réussie"
        FAILED = "failed", "Échec"

    reference = models.CharField(max_length=40, unique=True, editable=False)
    backup_type = models.CharField(max_length=20, choices=BackupType.choices, default=BackupType.DATABASE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    location = models.CharField(max_length=500, blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Sauvegarde"
        verbose_name_plural = "Sauvegardes"

    def __str__(self):
        return f"{self.reference} — {self.get_backup_type_display()} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = next_daily_reference(BackupRecord.objects.all(), "BAK")
        super().save(*args, **kwargs)

    def mark_success(self, *, size_bytes=None, location="", error=""):
        self.status = self.Status.SUCCESS
        self.size_bytes = size_bytes
        self.location = location
        self.finished_at = timezone.now()
        self.save(update_fields=["status", "size_bytes", "location", "finished_at"])

    def mark_failed(self, error):
        self.status = self.Status.FAILED
        self.error = error
        self.finished_at = timezone.now()
        self.save(update_fields=["status", "error", "finished_at"])


class EmergencyAccess(models.Model):
    """Accès d'urgence « break-the-glass » : ouverture hors circuit normal.

    Toute ouverture d'un accès technique élargi (par exemple contourner le
    mode maintenance, exécuter une action bloquée) est tracée ici : qui,
    quand, pourquoi, jusqu'à quand — pour la révision a posteriori.
    """
    class Status(models.TextChoices):
        ACTIVE = "active", "Actif"
        EXPIRED = "expired", "Expiré"
        REVOKED = "revoked", "Révoqué"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="emergency_accesses")
    title = models.CharField(max_length=255, help_text="Motif court (ex. « Contournement mode maintenance »)")
    reason = models.TextField(blank=True)
    scopes = models.JSONField(default=list, help_text="Liste des périmètres ouverts (ex. ['ops.manage', 'settings.manage'])")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Accès d'urgence"
        verbose_name_plural = "Accès d'urgence"

    def __str__(self):
        return f"Accès d'urgence — {self.title} ({self.user.email})"

    def is_active(self):
        if self.status != self.Status.ACTIVE:
            return False
        if self.expires_at and self.expires_at <= timezone.now():
            self.expire()
            return False
        return True

    def expire(self):
        if self.status == self.Status.ACTIVE:
            self.status = self.Status.EXPIRED
            self.save(update_fields=["status"])

    def revoke(self):
        self.status = self.Status.REVOKED
        self.save(update_fields=["status"])