"""
Notifications, produits sponsorisés, abonnements et factures.
"""
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.users.models import User
from apps.catalog.models import Product, Store


class Notification(models.Model):
    class Channel(models.TextChoices):
        EMAIL = 'email', 'Email'
        SMS = 'sms', 'SMS'
        PUSH = 'push', 'Push'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    channel = models.CharField(max_length=50, choices=Channel.choices)
    subject = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING)
    is_read = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def send(self):
        """Envoie la notification selon son canal (no-op pour push, pas encore implémenté)."""
        if self.channel == self.Channel.EMAIL:
            self._send_email()
        elif self.channel == self.Channel.SMS:
            self._send_sms()

    def _send_email(self):
        from django.conf import settings
        from django.core.mail import send_mail
        import logging

        logger = logging.getLogger(__name__)

        try:
            send_mail(self.subject, self.message, settings.DEFAULT_FROM_EMAIL, [self.user.email], fail_silently=False)
            self.mark_sent()
        except Exception:
            # Un SMTP injoignable ne doit pas être invisible : on trace la
            # cause exacte (quota, auth, réseau...) avant de marquer l'échec.
            logger.exception("Échec de l'envoi de la notification email à %s (sujet : %s)", self.user.email, self.subject)
            self.mark_failed()

    def _send_sms(self):
        """
        Aucun fournisseur SMS n'est configuré (Twilio, Africa's Talking,
        API SMS d'un opérateur local, etc.). Brancher l'appel ici une fois
        un fournisseur choisi et ses identifiants disponibles — en
        attendant, la notification reste tracée mais jamais réellement
        envoyée, pour ne pas prétendre à tort qu'un SMS est parti.
        """
        self.mark_failed()

    def mark_sent(self):
        self.status = self.Status.SENT
        self.sent_at = timezone.now()
        self.save()

    def mark_failed(self):
        self.status = self.Status.FAILED
        self.save()

    def __str__(self):
        return f"Notification for {self.user.email}"


class SponsoredProduct(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        EXPIRED = 'expired', 'Expired'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sponsorships')
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='sponsored_products')
    daily_budget = models.DecimalField(max_digits=10, decimal_places=2)
    starts_at = models.DateField()
    ends_at = models.DateField()
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.INACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_active(self):
        today = timezone.now().date()
        return self.status == self.Status.ACTIVE and self.starts_at <= today <= self.ends_at

    def __str__(self):
        return f"Sponsored {self.product.name}"


class SubscriptionPlan(models.Model):
    id = models.AutoField(primary_key=True)
    # Code d'offre stable et unique (STARTER / PRO / BUSINESS) — jamais
    # renommé, c'est la clé métier utilisée par les endpoints, tests et
    # paiements. `name` reste le libellé affichable.
    code = models.CharField(max_length=50, unique=True, null=True, blank=True)
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    billing_cycle = models.CharField(max_length=50)  # monthly, yearly
    features = models.JSONField(default=dict)
    # Nombre maximum de produits (publiés ou non) par boutique — None = illimité.
    # Sans ça, "Nombre limité / augmenté / illimité de produits" dans `features`
    # n'était que du texte marketing jamais réellement appliqué.
    max_products = models.IntegerField(null=True, blank=True)
    # Taux de commission (en %) prélevé sur les ventes du commerçant tant que
    # son abonnement est actif. Le taux est figé au moment de chaque vente —
    # une vente passée garde le taux de son plan d'alors (spec commission §12).
    # Lancement V1 : 0 % sur tous les plans (commission SUNU MALL 0 %).
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # Durée (en jours) d'une période d'abonnement achetée une seule fois
    # (spec §5). Remplit ends_at côté serveur (jamais fourni par le client).
    duration_days = models.IntegerField(default=30)
    # Un plan inactif n'est plus proposé ni appliqué aux nouvelles ventes.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Subscription(models.Model):
    class Status(models.TextChoices):
        # En attente de confirmation du paiement (voir apps.payments.Payment) —
        # une offre gratuite (price=0) saute directement à ACTIVE.
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        CANCELLED = 'cancelled', 'Cancelled'
        EXPIRED = 'expired', 'Expired'
        # Suspendu par un admin (fraude, litige...) : la suspension coupe
        # immédiatement la vente (spec monétisation §22/§24), sans supprimer
        # l'historique ni l'abonnement.
        SUSPENDED = 'suspended', 'Suspended'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Référence lisible par le vendeur, ex. SUB-20260909-A1B2C3 (spec §19) :
    # générée côté serveur au plus tard à la sauvegarde, jamais fournie par
    # le client. `null=True` le temps de la migration de backfill.
    reference = models.CharField(max_length=40, unique=True, editable=False, null=True, blank=True)
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name='subscriptions')
    subscriber_type = models.CharField(max_length=100)
    subscriber_id = models.UUIDField()
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING)
    starts_at = models.DateField()
    ends_at = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def make_reference(self):
        """SUB-YYYYMMDD-###### — suffixe dérivé de l'UUID (6 hex), unique par ligne."""
        day = timezone.now().strftime("%Y%m%d")
        suffix = (self.id.hex if self.id else uuid.uuid4().hex)[:6].upper()
        return f"SUB-{day}-{suffix}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self.make_reference()
        super().save(*args, **kwargs)

    def is_active(self):
        today = timezone.now().date()
        return self.status == self.Status.ACTIVE and self.starts_at <= today <= self.ends_at

    def in_grace(self, at=None):
        """Vrai tant que l'abonnement peut encore couvrir une période de grâce."""
        at = at or timezone.now().date()
        if self.status not in (self.Status.ACTIVE, self.Status.EXPIRED):
            return False
        grace_until = self.ends_at + timedelta(days=settings.SUBSCRIPTION_GRACE_PERIOD_DAYS)
        return at <= grace_until

    @property
    def days_left(self):
        if self.status != self.Status.ACTIVE:
            return 0
        return max(0, (self.ends_at - timezone.now().date()).days)

    def cancel(self):
        if self.status == self.Status.CANCELLED:
            return
        before = self.plan
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status"])
        self.record_history(
            SubscriptionHistory.Action.CANCELLED, old_plan=before, new_plan=before,
            old_end_date=self.ends_at, new_end_date=self.ends_at,
        )
        self._notify("Abonnement annulé", f"Votre abonnement « {self.plan.name} » a été annulé.")

    def suspend(self, performed_by=None):
        if self.status == self.Status.SUSPENDED:
            return
        self.status = self.Status.SUSPENDED
        self.save(update_fields=["status"])
        self.record_history(
            SubscriptionHistory.Action.SUSPENDED,
            old_plan=self.plan, new_plan=self.plan,
            old_end_date=self.ends_at, new_end_date=self.ends_at,
            performed_by=performed_by,
        )
        self._notify(
            "Abonnement suspendu",
            f"Votre abonnement « {self.plan.name} » a été suspendu par un administrateur.",
        )

    def renew(self):
        """Prolonge la période courante (ou en ouvre une nouvelle si échue).

        Appelé uniquement après confirmation backend du paiement de
        renouvellement (jamais directement par le client).
        """
        today = timezone.now().date()
        old_end = self.ends_at
        days = self.plan.duration_days or 30
        if self.is_active():
            self.ends_at = self.ends_at + timedelta(days=days)
        else:
            self.starts_at = today
            self.ends_at = today + timedelta(days=days)
        self.status = self.Status.ACTIVE
        self.save()
        self.record_history(
            SubscriptionHistory.Action.RENEWED,
            old_plan=self.plan, new_plan=self.plan,
            old_end_date=old_end, new_end_date=self.ends_at,
        )
        return old_end

    def change_plan(self, new_plan):
        """Change la formule et ouvre une nouvelle période (2 500 → 5 000 FCFA...).

        Appelé uniquement après confirmation backend du paiement du nouveau
        plan — l'ancien abonnement n'est jamais supprimé, il reste tracé
        dans SubscriptionHistory.
        """
        old_plan = self.plan
        old_end = self.ends_at
        today = timezone.now().date()
        self.plan = new_plan
        self.starts_at = today
        self.ends_at = today + timedelta(days=new_plan.duration_days or 30)
        self.status = self.Status.ACTIVE
        self.save()
        self.record_history(
            SubscriptionHistory.Action.PLAN_CHANGED,
            old_plan=old_plan, new_plan=new_plan,
            old_end_date=old_end, new_end_date=self.ends_at,
        )
        self._notify(
            "Formule modifiée",
            f"Votre abonnement est désormais « {new_plan.name} » jusqu'au "
            f"{self.ends_at.strftime('%d/%m/%Y')}.",
        )
        return old_plan

    def subscriber_user(self):
        # subscriber_type/subscriber_id est volontairement générique (pas de
        # FK) pour pouvoir accueillir d'autres types d'abonnés plus tard —
        # aujourd'hui seul "merchant" (un User) existe réellement.
        if self.subscriber_type != "merchant":
            return None
        return User.objects.filter(id=self.subscriber_id).first()

    def record_history(self, action, old_plan=None, new_plan=None,
                       old_end_date=None, new_end_date=None,
                       performed_by=None, metadata=None):
        """Trace un événement du cycle de vie (jamais supprimé ensuite)."""
        seller = self.subscriber_user()
        SubscriptionHistory.objects.create(
            subscription=self,
            seller=seller if seller else None,
            old_plan=old_plan,
            new_plan=new_plan,
            old_end_date=old_end_date,
            new_end_date=new_end_date,
            action=action,
            performed_by=performed_by,
            metadata=metadata or {},
        )

    def notify_activated(self):
        message = (
            f"Bonjour,\n\nVotre abonnement « {self.plan.name} » est actif jusqu'au "
            f"{self.ends_at.strftime('%d/%m/%Y')}.\n\nMerci de votre confiance !"
        )
        self._notify(f"Abonnement « {self.plan.name} » activé", message)

    def notify_expiring_soon(self, days_left):
        message = (
            f"Bonjour,\n\nVotre abonnement « {self.plan.name} » expire dans {days_left} jour"
            f"{'s' if days_left > 1 else ''} (le {self.ends_at.strftime('%d/%m/%Y')}). "
            "Renouvelez-le depuis votre espace pour ne pas perdre vos avantages."
        )
        self._notify(f"Votre abonnement « {self.plan.name} » expire bientôt", message)

    def notify_expired(self):
        message = (
            f"Bonjour,\n\nVotre abonnement « {self.plan.name} » a expiré le "
            f"{self.ends_at.strftime('%d/%m/%Y')}. Renouvelez-le depuis votre espace pour "
            "retrouver ses avantages."
        )
        self._notify(f"Abonnement « {self.plan.name} » expiré", message)

    def _notify(self, subject, message):
        user = self.subscriber_user()
        if not user:
            return
        notification = Notification.objects.create(
            user=user, channel=Notification.Channel.EMAIL, subject=subject, message=message,
            metadata={"subscription_id": str(self.id)},
        )
        notification.send()

    def __str__(self):
        return f"Subscription {self.id} - {self.plan.name}"


class SubscriptionHistory(models.Model):
    """Historique immuable du cycle de vie d'un abonnement (spec monétisation §6).

    Chaque changement (activation, renouvellement, changement de formule,
    expiration, annulation, suspension) est tracé avec l'ancienne et la
    nouvelle formule et les dates avant/après. Jamais supprimé — même un
    changement de plan conserve la trace de l'ancien abonnement.
    """

    class Action(models.TextChoices):
        CREATED = "created", "Created"
        ACTIVATED = "activated", "Activated"
        RENEWED = "renewed", "Renewed"
        PLAN_CHANGED = "plan_changed", "Plan changed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"
        SUSPENDED = "suspended", "Suspended"

    id = models.AutoField(primary_key=True)
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="history")
    seller = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    action = models.CharField(max_length=20, choices=Action.choices)
    old_plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    new_plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    old_end_date = models.DateField(null=True, blank=True)
    new_end_date = models.DateField(null=True, blank=True)
    # Qui a déclenché le changement (null = le système : tâche Celery, webhook).
    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="subscription_history_actions"
    )
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.subscription_id} - {self.created_at:%Y-%m-%d %H:%M}"


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ISSUED = 'issued', 'Issued'
        PAID = 'paid', 'Paid'
        OVERDUE = 'overdue', 'Overdue'
        CANCELLED = 'cancelled', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='invoices')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.DRAFT)
    issued_at = models.DateField(null=True, blank=True)
    due_at = models.DateField(null=True, blank=True)
    paid_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def mark_paid(self):
        self.status = self.Status.PAID
        self.paid_at = timezone.now().date()
        self.save()

    def is_overdue(self):
        if self.status == self.Status.ISSUED and self.due_at and timezone.now().date() > self.due_at:
            return True
        return False

    def __str__(self):
        return f"Invoice {self.id} - {self.subscription.id}"
