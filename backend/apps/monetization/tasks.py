"""
Tâches Celery de l'app monétisation (abonnements, notifications génériques).

Ces traitements étaient historiquement déclenchés à la lecture de la liste
des abonnements (SubscriptionViewSet.get_queryset) : un simple GET faisait
des écritures en base et envoyait des emails, un N+1 d'écriture/email défavorable.
On les déplace ici, exécutés périodiquement par Celery Beat (voir
CELERY_BEAT_SCHEDULE dans config/settings/base.py) — la lecture redevient
une lecture.
"""
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.monetization.models import Notification, Subscription, SubscriptionHistory


@shared_task
def expire_and_remind_subscriptions():
    """Passe les abonnements échus à "expired" et envoie les rappels "expire bientôt".

    Idempotent : on ne notifie chaque abonnement qu'une seule fois (un rappel
    "expire bientôt" n'est envoyé que si aucune notification de ce type
    n'existe déjà pour lui, à J-7 / J-3 / J-1 — configurables via
    settings.SUBSCRIPTION_REMINDER_DAYS). À exécuter quotidiennement via
    Celery Beat.
    """
    today = timezone.now().date()

    # Auto-expiration des abonnements actifs dont la date de fin est dépassée
    # (hors période de grâce, gérée par l'entitlement commission : le vendeur
    # continue de vendre pendant SUBSCRIPTION_GRACE_PERIOD_DAYS, spec §11).
    for subscription in Subscription.objects.filter(
        status=Subscription.Status.ACTIVE, ends_at__lt=today
    ):
        subscription.status = Subscription.Status.EXPIRED
        subscription.save(update_fields=["status"])
        subscription.record_history(
            SubscriptionHistory.Action.EXPIRED,
            old_plan=subscription.plan, new_plan=subscription.plan,
            old_end_date=subscription.ends_at, new_end_date=subscription.ends_at,
        )
        subscription.notify_expired()
        # Entitlement commission du vendeur synchronisé (spec §17-§18) :
        # au-delà de la période de grâce le vendeur ne reçoit plus de commande.
        from apps.commissions.services import sync_plan_from_subscription
        sync_plan_from_subscription(subscription)

    # Rappel unique "expire bientôt" à chaque horizon configuré (J-7, J-3, J-1).
    for days in settings.SUBSCRIPTION_REMINDER_DAYS:
        target = today + timedelta(days=days)
        expiring = Subscription.objects.filter(
            status=Subscription.Status.ACTIVE, ends_at=target
        )
        for subscription in expiring:
            already_notified = Notification.objects.filter(
                metadata__subscription_id=str(subscription.id),
                metadata__kind=f"expire_soon_d{days}",
            ).exists()
            user = subscription.subscriber_user()
            if already_notified or user is None:
                continue
            Notification.objects.create(
                user=user,
                channel=Notification.Channel.EMAIL,
                subject=f"Votre abonnement « {subscription.plan.name} » expire bientôt",
                message=(
                    f"Bonjour,\n\nVotre abonnement « {subscription.plan.name} » expire dans "
                    f"{days} jour{'s' if days > 1 else ''} (le {subscription.ends_at.strftime('%d/%m/%Y')}). "
                    "Renouvelez-le depuis votre espace pour ne pas perdre vos avantages."
                ),
                metadata={"subscription_id": str(subscription.id), "kind": f"expire_soon_d{days}"},
            ).send()