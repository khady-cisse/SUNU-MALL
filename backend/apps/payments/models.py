"""
Paiements, commissions, transactions et remboursements.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone
from apps.orders.models import Order
from apps.monetization.models import Invoice, Subscription, SubscriptionHistory


class CommissionRule(models.Model):
    id = models.AutoField(primary_key=True)
    applies_to = models.CharField(max_length=100)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def current_rate(applies_to):
        now = timezone.now()
        rule = CommissionRule.objects.filter(
            applies_to=applies_to,
            valid_from__lte=now
        ).filter(
            models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=now)
        ).first()
        return rule.percentage if rule else Decimal("0")

    def __str__(self):
        return f"{self.applies_to} - {self.percentage}%"


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Un paiement règle soit une commande, soit une commande globale
    # multi-boutiques, soit un abonnement — jamais deux à la fois (contrainte
    # ci-dessous) : d'où les FK optionnelles plutôt qu'une relation polymorphe.
    # Un abonnement peut avoir PLUSIEURS paiements (souscription initiale,
    # renouvellement, changement de formule) : FK, pas OneToOne.
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment', null=True, blank=True)
    global_order = models.ForeignKey(
        'orders.GlobalOrder', on_delete=models.CASCADE, related_name='payments', null=True, blank=True
    )
    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name='payments', null=True, blank=True
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="XOF")
    method = models.CharField(max_length=100)
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING)
    provider_ref = models.CharField(max_length=255, blank=True)
    # Intent du paiement d'abonnement, posé au moment de sa création par le
    # backend — jamais par le client :
    #   {"action": "subscribe"}            nouvelle souscription
    #   {"action": "renew"}                renouvellement de la formule courante
    #   {"action": "change_plan",
    #    "plan_code": "PRO"}               montée/descente de formule
    # Permet à mark_succeeded de savoir quoi faire à la confirmation sans
    # qu'aucune valeur décisionnelle ne vienne du frontend.
    metadata = models.JSONField(default=dict)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(order__isnull=False, global_order__isnull=True, subscription__isnull=True)
                    | models.Q(order__isnull=True, global_order__isnull=False, subscription__isnull=True)
                    | models.Q(order__isnull=True, global_order__isnull=True, subscription__isnull=False)
                ),
                name='payment_targets_one_billing_object',
            )
        ]

    def mark_succeeded(self):
        """Marque le paiement réussi et déclenche enfin le traitement métier.

        Idempotent : un second appel (webhook rejoué, sandbox-confirm
        rappelée) ne ré-exécute rien — la commission d'une commande n'est
        donc jamais créditée deux fois (spec commission §27-§28), et un
        renouvellement d'abonnement n'allonge jamais deux fois la période.
        """
        if self.status == self.Status.SUCCESS:
            return
        self.status = self.Status.SUCCESS
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at"])
        if self.subscription_id:
            self._activate_subscription()
            from apps.commissions.services import (
                register_subscription_revenue, sync_plan_from_subscription,
            )
            sync_plan_from_subscription(self.subscription)
            register_subscription_revenue(self.subscription, self.amount)
        elif self.global_order_id:
            # Paiement global multi-boutiques : une transaction globale est
            # tracée, puis la commission de chaque sous-commande est réglée
            # individuellement (par vendeur) — jamais deux fois.
            Transaction.objects.create(
                payment=self,
                type=Transaction.Type.SALE,
                payee_type="global_order",
                payee_id=self.global_order_id,
                amount=self.amount,
            )
            from apps.commissions.services import settle_commission_for_order

            for sub_order in self.global_order.orders.filter(status="pending"):
                sub_order.change_status(sub_order.Status.PAID)
                settle_commission_for_order(sub_order)
            if self.global_order.status == "pending":
                self.global_order.status = "paid"
                self.global_order.save(update_fields=["status"])
        else:
            Transaction.create_for_payment(self)
            from apps.commissions.services import settle_commission_for_order
            settle_commission_for_order(self.order)

    def _activate_subscription(self):
        subscription = self.subscription
        intent = self.metadata or {}
        action = intent.get("action", "subscribe")
        today = timezone.now().date()

        if action == "renew":
            subscription.renew()
        elif action == "change_plan":
            from apps.monetization.models import SubscriptionPlan

            plan = SubscriptionPlan.objects.filter(
                code=intent.get("plan_code"), is_active=True
            ).first()
            # Un intent invalide (plan_code inconnu) ne casse jamais une
            # activation : on conserve la formule courante.
            subscription.change_plan(plan or subscription.plan)
        elif subscription.status == Subscription.Status.PENDING:
            # Souscription initiale : les dates ont été calculées à la
            # création (jamais fournies par le client).
            subscription.status = Subscription.Status.ACTIVE
            subscription.save(update_fields=["status"])
            subscription.record_history(
                SubscriptionHistory.Action.ACTIVATED,
                old_plan=subscription.plan, new_plan=subscription.plan,
                old_end_date=subscription.ends_at, new_end_date=subscription.ends_at,
            )
            subscription.notify_activated()
        else:
            # Réactivation d'un abonnement échu/annulé : nouvelle période.
            subscription.starts_at = today
            subscription.ends_at = today + timedelta(days=subscription.plan.duration_days or 30)
            subscription.status = Subscription.Status.ACTIVE
            subscription.save()
            subscription.record_history(
                SubscriptionHistory.Action.ACTIVATED,
                old_plan=subscription.plan, new_plan=subscription.plan,
                old_end_date=None, new_end_date=subscription.ends_at,
            )
            subscription.notify_activated()

        invoice = Invoice.objects.create(
            subscription=subscription, amount=self.amount,
            status=Invoice.Status.ISSUED, issued_at=today, due_at=today,
        )
        invoice.mark_paid()

    def mark_failed(self):
        self.status = self.Status.FAILED
        self.save()
        if self.subscription_id:
            # Une souscription initiale en attente est annulée ; un
            # renouvellement/changement de formule échoué ne coupe JAMAIS
            # l'abonnement déjà actif (le client garde sa formule).
            if self.subscription.status == Subscription.Status.PENDING:
                self.subscription.cancel()
            else:
                self._notify_payment_failed()

    def _notify_payment_failed(self):
        from apps.monetization.models import Notification

        subscription = self.subscription
        user = subscription.subscriber_user()
        if not user:
            return
        notification = Notification.objects.create(
            user=user, channel=Notification.Channel.EMAIL,
            subject=f"Paiement « {subscription.plan.name} » échoué",
            message=(
                f"Bonjour,\n\nLe paiement de votre abonnement "
                f"« {subscription.plan.name} » ({self.amount} FCFA) a échoué. "
                "Votre formule actuelle reste active. Réessayez depuis votre espace."
            ),
            metadata={"subscription_id": str(subscription.id), "payment_id": str(self.id)},
        )
        notification.send()

    def __str__(self):
        return f"Payment {self.id} - {self.order_id or self.subscription_id}"


class Transaction(models.Model):
    class Type(models.TextChoices):
        SALE = 'sale', 'Sale'
        COMMISSION = 'commission', 'Commission'
        REFUND = 'refund', 'Refund'

    id = models.AutoField(primary_key=True)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='transactions')
    type = models.CharField(max_length=50, choices=Type.choices)
    payee_type = models.CharField(max_length=100)
    # Null pour la part plateforme (COMMISSION) : ce n'est pas un utilisateur,
    # il n'y a donc pas d'UUID réel à renseigner.
    payee_id = models.UUIDField(null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50, default='completed')
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def create_for_payment(payment):
        """
        Ventile un paiement de commande réussi entre le commerçant (part
        vente) et la plateforme (commission), selon le taux configuré dans
        CommissionRule (0% si aucune règle "order" n'est active). Ne
        s'applique qu'aux paiements de commande — un paiement d'abonnement
        est déjà entièrement un revenu plateforme, tracé via Invoice.
        """
        if payment.order_id is None:
            return

        rate = CommissionRule.current_rate("order")
        commission_amount = (payment.amount * rate / Decimal("100")).quantize(Decimal("0.01"))
        seller_amount = payment.amount - commission_amount

        Transaction.objects.create(
            payment=payment, type=Transaction.Type.SALE,
            payee_type="merchant", payee_id=payment.order.store.owner_id,
            amount=seller_amount,
        )
        if commission_amount > 0:
            Transaction.objects.create(
                payment=payment, type=Transaction.Type.COMMISSION,
                payee_type="platform", payee_id=None,
                amount=commission_amount,
            )

    def __str__(self):
        return f"Transaction {self.id} - {self.type}"


class Refund(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        COMPLETED = 'completed', 'Completed'

    id = models.AutoField(primary_key=True)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING)
    refunded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def process(self):
        """
        Marque le remboursement traité : passe le paiement à "refunded",
        contre-passe chaque transaction déjà enregistrée (vente + commission)
        par une transaction REFUND de signe opposé, puis prévient le client.
        Appelé par un admin (voir RefundViewSet.process) — un remboursement
        Wave/Orange Money/carte n'est pas un appel API instantané ici, un
        humain confirme que l'argent a bien été renvoyé avant ce statut.
        """
        self.status = self.Status.COMPLETED
        self.refunded_at = timezone.now()
        self.save()

        payment = self.payment
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status"])

        for original in payment.transactions.exclude(type=Transaction.Type.REFUND):
            Transaction.objects.create(
                payment=payment, type=Transaction.Type.REFUND,
                payee_type=original.payee_type, payee_id=original.payee_id,
                amount=-original.amount,
            )

        # Commission : contre-passe la vente (fonds vendeur + commission plateforme).
        from apps.commissions.services import reverse_commission_for_refund
        reverse_commission_for_refund(self)

        self._notify_customer()

    def _notify_customer(self):
        from apps.monetization.models import Notification

        order = self.payment.order
        if not order:
            return
        subject = f"Remboursement traité — {order.store.name}"
        message = (
            f"Bonjour {order.customer.first_name or order.customer.email},\n\n"
            f"Le remboursement de {self.amount} FCFA pour votre commande n°{str(order.id)[:8]} "
            "a bien été traité.\n\nMerci de votre compréhension."
        )
        notification = Notification.objects.create(
            user=order.customer, channel=Notification.Channel.EMAIL,
            subject=subject, message=message,
            metadata={"refund_id": str(self.id), "order_id": str(order.id)},
        )
        notification.send()

    def __str__(self):
        return f"Refund {self.id} - {self.payment.id}"
