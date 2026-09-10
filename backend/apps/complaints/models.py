"""
Modèles du support client : plaintes/litiges et tickets de support.

La timeline d'une plainte est IMMUTABLE (écriture seule, historique conservé) :
elle sert de preuve de la gestion du litige. Les références
PLT-/TKT-YYYYMMDD-NNNNNN sont générées côté serveur.
"""
import uuid

from django.db import models
from django.utils import timezone

from apps.orders.models import Delivery, Driver, Order
from apps.payments.models import Payment
from apps.users.models import User

from .pdf import next_daily_reference


class Complaint(models.Model):
    """Plainte déposée par un client (litige) ou un acteur (vendeur/livreur)."""

    class Category(models.TextChoices):
        ORDER_NOT_RECEIVED = "order_not_received", "Commande non reçue"
        WRONG_ITEM = "wrong_item", "Article incorrect"
        DEFECTIVE_PRODUCT = "defective_product", "Produit défectueux"
        LATE_DELIVERY = "late_delivery", "Livraison en retard"
        DAMAGED_DURING_DELIVERY = "damaged_during_delivery", "Colis endommagé à la livraison"
        INCORRECT_CHARGE = "incorrect_charge", "Montant prélevé incorrect"
        REFUND_ISSUE = "refund_issue", "Problème de remboursement"
        SELLER_BEHAVIOR = "seller_behavior", "Comportement du vendeur"
        DRIVER_BEHAVIOR = "driver_behavior", "Comportement du livreur"
        QUALITY_ISSUE = "quality_issue", "Problème de qualité"
        SUBSCRIPTION_ISSUE = "subscription_issue", "Problème d'abonnement"
        OTHER = "other", "Autre"

    class Priority(models.TextChoices):
        LOW = "low", "Basse"
        MEDIUM = "medium", "Moyenne"
        HIGH = "high", "Haute"
        CRITICAL = "critical", "Critique"

    class Status(models.TextChoices):
        OPEN = "open", "Ouverte"
        ASSIGNED = "assigned", "Assignée"
        IN_PROGRESS = "in_progress", "En cours de traitement"
        ESCALATED = "escalated", "Escaladée"
        RESOLVED = "resolved", "Résolue"
        CLOSED = "closed", "Clos"

    class Decision(models.TextChoices):
        REFUND = "refund", "Remboursement"
        EXCHANGE = "exchange", "Remplacement / échange"
        RETURN = "return", "Retour produit"
        COMPENSATION = "compensation", "Indemnisation"
        INFO = "info", "Information donnée"
        NO_ACTION = "no_action", "Aucune action requise"

    # Statuts considérés comme "ouverts" (non terminés) — pour les alertes.
    OPEN_STATUSES = [Status.OPEN, Status.ASSIGNED, Status.IN_PROGRESS, Status.ESCALATED]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=40, unique=True, editable=False)

    # Émetteur de la plainte (client, vendeur ou livreur selon le cas).
    complainant = models.ForeignKey(User, on_delete=models.CASCADE, related_name="submitted_complaints")

    # Objet du litige (identifiants d'objets, jamais de copies sensibles).
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="complaints")
    store = models.ForeignKey("catalog.Store", on_delete=models.SET_NULL, null=True, blank=True, related_name="complaints")
    delivery = models.ForeignKey(Delivery, on_delete=models.SET_NULL, null=True, blank=True, related_name="complaints")
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True, related_name="complaints")
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="complaints")

    category = models.CharField(max_length=50, choices=Category.choices, default=Category.OTHER)
    subject = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    # Traitement par le support.
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="assigned_complaints")
    resolution_decision = models.CharField(max_length=30, choices=Decision.choices, blank=True)
    resolution_note = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Plainte"
        verbose_name_plural = "Plaintes"

    def __str__(self):
        return f"{self.reference} — {self.subject}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = next_daily_reference(Complaint.objects.all(), "PLT")
        super().save(*args, **kwargs)

    def append_timeline(self, actor, action, note="", metadata=None):
        """Étape d'historique (append-only) de la plainte."""
        return ComplaintTimeline.objects.create(
            complaint=self, actor=actor, action=action, note=note, metadata=metadata or {},
        )


class ComplaintTimeline(models.Model):
    """Étapes de traitement d'une plainte. Adjunction seule : pas de mise à
    jour ni de suppression (historique probant conservé intact)."""
    class Action(models.TextChoices):
        CREATED = "created", "Déposée"
        ASSIGNED = "assigned", "Assignée"
        STARTED = "started", "Traitement commencé"
        ESCALATED = "escalated", "Escaladée"
        RESPONDED = "responded", "Réponse apportée"
        RESOLVED = "resolved", "Résolue"
        CLOSED = "closed", "Clos"
        REOPENED = "reopened", "Rouverte"
        NOTE = "note", "Note interne"

    id = models.BigAutoField(primary_key=True)
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="timeline")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Étape de plainte"
        verbose_name_plural = "Étapes de plainte"

    def delete(self, *args, **kwargs):
        raise NotImplementedError("L'historique d'une plainte est immuable (append-only).")


class ComplaintAttachment(models.Model):
    """Pièce jointe d'une plainte (décrit un objet stocké côté objet utilisateur).

    V1 : on conserve uniquement les métadonnées du fichier (référence de
    stockage, type, taille) — pas d'upload multipart via l'API admin."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="attachments")
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    storage_key = models.CharField(max_length=500)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.filename


class SupportTicket(models.Model):
    """Ticket de support posé par un utilisateur (vendeur/client/livreur)."""

    class Category(models.TextChoices):
        QUESTION = "question", "Question"
        HELP = "help", "Aide / assistance"
        ACCOUNT = "account", "Problème de compte"
        PAYMENT = "payment", "Paiement"
        SUBSCRIPTION = "subscription", "Abonnement"
        TECH = "tech", "Problème technique"
        OTHER = "other", "Autre"

    class Status(models.TextChoices):
        NEW = "new", "Nouveau"
        OPEN = "open", "Ouvert"
        ANSWERED = "answered", "Répondu"
        RESOLVED = "resolved", "Résolu"
        CLOSED = "closed", "Clos"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=40, unique=True, editable=False)
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name="support_tickets")
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.QUESTION)
    subject = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="assigned_tickets")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Ticket de support"
        verbose_name_plural = "Tickets de support"

    def __str__(self):
        return f"{self.reference} — {self.subject}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = next_daily_reference(SupportTicket.objects.all(), "TKT")
        super().save(*args, **kwargs)


class TicketMessage(models.Model):
    """Message d'un ticket (requérant ou support)."""
    id = models.BigAutoField(primary_key=True)
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    body = models.TextField()
    is_support_reply = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Message {self.id} — {self.ticket.reference}"
