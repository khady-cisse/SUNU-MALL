"""
Notifications, produits sponsorisés, abonnements et factures.
"""
import uuid
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
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    billing_cycle = models.CharField(max_length=50)  # monthly, yearly
    features = models.JSONField(default=dict)
    # Nombre maximum de produits ACTIFS (publiés) par boutique — None = illimité.
    # Sans ça, "Nombre limité / augmenté / illimité de produits" dans `features`
    # n'était que du texte marketing jamais réellement appliqué.
    max_products = models.IntegerField(null=True, blank=True)
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name='subscriptions')
    subscriber_type = models.CharField(max_length=100)
    subscriber_id = models.UUIDField()
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING)
    starts_at = models.DateField()
    ends_at = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_active(self):
        today = timezone.now().date()
        return self.status == self.Status.ACTIVE and self.starts_at <= today <= self.ends_at

    def cancel(self):
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status"])
        self._notify("Abonnement annulé", f"Votre abonnement « {self.plan.name} » a été annulé.")

    def subscriber_user(self):
        # subscriber_type/subscriber_id est volontairement générique (pas de
        # FK) pour pouvoir accueillir d'autres types d'abonnés plus tard —
        # aujourd'hui seul "merchant" (un User) existe réellement.
        if self.subscriber_type != "merchant":
            return None
        return User.objects.filter(id=self.subscriber_id).first()

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
