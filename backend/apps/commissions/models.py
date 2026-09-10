"""
Commissions SUNU MALL, portefeuilles vendeurs et ledger des fonds
(spec commissions §1-§33).

Principes portés par ce module :
- le montant brut et la commission ne sont JAMAIS calculés côté frontend :
  ils sont redérivés en base à chaque vente (produit, quantité, prix officiel,
  vendeur, plan, taux) au moment où le paiement est confirmé (§6-§8) ;
- chaque vente fige le taux de commission de son plan d'alors — une vente
  passée n'est jamais recalculée (§12) ;
- chaque mouvement d'argent est tracé dans un ledger (WalletTransaction /
  PlatformTransaction) avec soldes avant/après pour chaque vendeur (§10) ;
- toutes les écritures d'une vente sont atomiques et idempotentes (contrainte
  unique (commande, vendeur) + égide du paiement déjà marqué succès) (§26-§28) ;
- les montants sont des Decimal (jamais de float) et chaque opération est
  arrondie de façon identique (§29).
"""
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.orders.models import Order
from apps.users.models import User


class SellerSubscription(models.Model):
    """Entitlement commission d'un vendeur (spec §4, §16-§18).

    Cycle de vie : chaque vendeur démarre avec 30 jours d'essai à 0 % de
    commission (trial_started_at = création du compte, trial_ends_at = +30 j).
    À la fin de l'essai il choisit un plan (STARTER/PRO/BUSINESS) : statut
    ACTIVE et période starts_at/ends_at renseignées. Passée la fin de période
    (ou de l'essai), le vendeur reste autorisé à vendre pendant une période de
    grâce configurable (COMMISSION_GRACE_DAYS) au taux de son dernier plan ;
    au-delà, il ne peut plus recevoir de commandes (§17-§18) — les données
    existantes ne sont jamais supprimées.
    """

    class Plan(models.TextChoices):
        STARTER = "STARTER", "STARTER"
        PRO = "PRO", "PRO"
        BUSINESS = "BUSINESS", "BUSINESS"

    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"
        SUSPENDED = "suspended", "Suspended"

    seller = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="commission_subscription"
    )
    # Instantané du plan choisi (nom de SubscriptionPlan). Vide tant que le
    # vendeur est en essai ou n'a jamais payé de plan. Le taux réellement
    # prélevé provient de SubscriptionPlan.commission_rate, lue au moment de
    # chaque vente — jamais d'ici.
    plan = models.CharField(max_length=20, choices=Plan.choices, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL)
    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def get_or_create_for(cls, seller):
        """Abonnement commission du vendeur, créé à la volée si absent.

        L'essai démarre à la création du compte (spec §3) — y compris pour
        les comptes créés avant l'arrivée de ce module.
        """
        trial_start = seller.created_at or timezone.now()
        subscription, _ = cls.objects.get_or_create(
            seller=seller,
            defaults={
                "status": cls.Status.TRIAL,
                "trial_started_at": trial_start,
                "trial_ends_at": trial_start + timedelta(days=settings.COMMISSION_TRIAL_DAYS),
            },
        )
        return subscription

    @staticmethod
    def _fallback_rate():
        from apps.monetization.models import SubscriptionPlan

        rates = (
            SubscriptionPlan.objects.filter(is_active=True)
            .order_by("commission_rate")
            .values_list("commission_rate", flat=True)
        )
        return rates[0] if rates else Decimal("0")

    def plan_obj(self):
        from apps.monetization.models import SubscriptionPlan

        if not self.plan:
            return None
        return SubscriptionPlan.objects.filter(name=self.plan, is_active=True).first()

    def trial_active(self, at=None):
        at = at or timezone.now()
        return (
            self.status == self.Status.TRIAL
            and self.trial_ends_at is not None
            and at <= self.trial_ends_at
        )

    def period_active(self, at=None):
        at = at or timezone.now()
        return (
            self.status == self.Status.ACTIVE
            and self.starts_at is not None and self.ends_at is not None
            and self.starts_at <= at <= self.ends_at
        )

    def grace_ends_at(self):
        anchor = self.ends_at or self.trial_ends_at
        if anchor is None:
            return None
        return anchor + timedelta(days=settings.COMMISSION_GRACE_DAYS)

    def in_grace(self, at=None):
        """Vrai tant que le vendeur peut encore vendre après la fin d'une période."""
        at = at or timezone.now()
        grace_ends = self.grace_ends_at()
        if grace_ends is None:
            return True
        return at <= grace_ends

    def resolve_rate(self, at=None):
        """(taux %, libellé du plan, autorisé à vendre) à un instant donné (§12, §16-§18).

        L'essai actif = 0 % ; un plan actif = son taux ; une période expirée
        = le taux du dernier plan pendant la grâce ; sans plan choisi, on
        retombe sur le taux minimal des plans actifs (Sunu Mall ne descend
        jamais en dessous de son offre la plus accessible).
        """
        at = at or timezone.now()
        if self.status == self.Status.SUSPENDED:
            # Suspension (admin) : coupe immédiatement la vente, sans grâce.
            return self._fallback_rate(), self.plan, False
        if self.trial_active(at):
            return Decimal("0"), "", True
        if self.period_active(at):
            plan = self.plan_obj()
            if plan:
                return plan.commission_rate, self.plan, True
        if self.status == self.Status.CANCELLED:
            return self._fallback_rate(), self.plan, False
        if not self.in_grace(at):
            return self._fallback_rate(), self.plan, False
        plan = self.plan_obj()
        if plan:
            return plan.commission_rate, self.plan, True
        return self._fallback_rate(), "", True

    @property
    def effective_status(self):
        """Statut réel calculé, indépendant du statut stocké (source de vérité)."""
        now = timezone.now()
        if self.status == self.Status.SUSPENDED:
            return self.Status.SUSPENDED
        if self.trial_active(now):
            return self.Status.TRIAL
        if self.period_active(now):
            return self.Status.ACTIVE
        if self.status == self.Status.CANCELLED:
            return self.Status.CANCELLED
        return self.Status.EXPIRED

    def apply_paid_plan(self, name, starts, ends):
        """Active le plan payé (appelé à la confirmation du paiement d'abonnement)."""
        self.plan = name
        self.status = self.Status.ACTIVE
        self.starts_at = starts
        self.ends_at = ends
        self.save()

    def mark_expired(self):
        if self.status == self.Status.ACTIVE:
            self.status = self.Status.EXPIRED
            self.save(update_fields=["status"])

    def mark_cancelled(self):
        if self.status != self.Status.CANCELLED:
            self.status = self.Status.CANCELLED
            self.save(update_fields=["status"])

    def mark_suspended(self):
        if self.status != self.Status.SUSPENDED:
            self.status = self.Status.SUSPENDED
            self.save(update_fields=["status"])

    def __str__(self):
        return f"SellerSubscription {self.seller_id} - {self.effective_status}"

    # Le triplet sert à la fois au calcul de la commission et au gating du checkout.
    def entitlement(self, at=None):
        at = at or timezone.now()
        rate, label, allowed = self.resolve_rate(at)
        return {"rate": rate, "plan": label, "allowed": allowed}


class SellerWallet(models.Model):
    """Portefeuille du vendeur (spec §9).

    `pending_balance` : fonds des ventes pas encore libérés (période de
    libération COMMISSION_RELEASE_DAYS). `available_balance` : solde
    effectivement retirable. Un remboursement peut rendre `available_balance`
    négatif si le vendeur a déjà retiré les fonds (dette assumée, §21).
    """

    seller = models.OneToOneField(User, on_delete=models.CASCADE, related_name="seller_wallet")
    available_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    pending_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_earned = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_withdrawn = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_or_create_for(cls, seller):
        wallet, _ = cls.objects.get_or_create(seller=seller)
        return wallet

    def __str__(self):
        return f"SellerWallet {self.seller_id} - {self.available_balance} dispo / {self.pending_balance} en attente"


class WalletTransaction(models.Model):
    """Ledger d'un portefeuille vendeur (spec §10).

    Chaque ligne porte le solde disponible et le solde en attente avant/après
    le mouvement — on peut reconstituer tout l'historique sans ambiguïté et
    contrôler qu'aucun mouvement n'est perdu (§33).
    """

    class Type(models.TextChoices):
        SALE = "sale", "Sale"                # +pending (vente réglée)
        COMMISSION = "commission", "Commission"
        REFUND = "refund", "Refund"          # -fonds sur remboursement (§20)
        PAYOUT = "payout", "Payout"          # -available (retrait demandé)
        RELEASE = "release", "Release"       # pending → available (libération)
        ADJUSTMENT = "adjustment", "Adjustment"

    id = models.AutoField(primary_key=True)
    wallet = models.ForeignKey(SellerWallet, on_delete=models.CASCADE, related_name="transactions")
    type = models.CharField(max_length=50, choices=Type.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    available_before = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    available_after = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    pending_before = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    pending_after = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    # Référence métier unique du mouvement (commande, remboursement, retrait...).
    reference = models.CharField(max_length=255, db_index=True)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"WalletTransaction {self.id} - {self.type} {self.amount}"


class CommissionTransaction(models.Model):
    """Vente ventilée par vendeur (spec §13-§15).

    Une commande appartient à un seul vendeur (le panier découpe déjà une
    commande par boutique) ; la contrainte unique (order, seller) rend le
    calcul idempotent : le double rappel d'un webhook ne crédite jamais deux
    fois le même vendeur (§27-§28).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="commission_transactions")
    seller = models.ForeignKey(User, on_delete=models.PROTECT, related_name="commission_transactions")
    # Instantané du plan au moment de la vente (STARTER/PRO/BUSINESS ou essai).
    plan = models.CharField(max_length=20, blank=True)
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2)   # éligible : hors livraison
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)  # jamais recalculé après coup
    commission_amount = models.DecimalField(max_digits=14, decimal_places=2)
    seller_amount = models.DecimalField(max_digits=14, decimal_places=2)   # net + frais de livraison
    is_refunded = models.BooleanField(default=False)
    refunded_at = models.DateTimeField(null=True, blank=True)
    is_released = models.BooleanField(default=False)  # pending → available
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["order", "seller"], name="commission_unique_order_seller")
        ]

    def __str__(self):
        return f"Commission #{str(self.order_id)[:8]} - {self.plan} {self.commission_rate}% - {self.commission_amount}"


class PlatformWallet(models.Model):
    """Compte de la plateforme pour les commissions et les abonnements (spec §22).

    Instance unique (pk=1). `balance` est un solde courant ; les lignes
    PlatformTransaction reconstituent l'historique.
    """

    id = models.AutoField(primary_key=True)
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_commissions = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_subscriptions = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_refunds = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_payouts = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def singleton(cls):
        wallet, _ = cls.objects.get_or_create(pk=1)
        return wallet

    def __str__(self):
        return f"PlatformWallet balance={self.balance}"


class PlatformTransaction(models.Model):
    """Ledger plateforme : commission, abonnement, remboursement, retrait."""

    class Type(models.TextChoices):
        COMMISSION = "commission", "Commission"
        SUBSCRIPTION = "subscription", "Subscription"
        REFUND = "refund", "Refund"
        PAYOUT = "payout", "Payout"
        ADJUSTMENT = "adjustment", "Adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(PlatformWallet, on_delete=models.CASCADE, related_name="transactions")
    type = models.CharField(max_length=50, choices=Type.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)  # signé
    reference = models.CharField(max_length=255, db_index=True)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PlatformTransaction {self.type} {self.amount}"


class Payout(models.Model):
    """Demande de retrait du vendeur (spec §19).

    Un retrait ne porte que sur `available_balance` (jamais sur les fonds en
    attente de libération), et uniquement si le KYC du vendeur est vérifié.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.PROTECT, related_name="payouts")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=100, default="wave")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reference = models.CharField(max_length=255, blank=True, unique=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payout {self.amount} - {self.seller_id} ({self.status})"