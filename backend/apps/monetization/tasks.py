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
from django.utils import timezone

from apps.monetization.models import Notification, Subscription


@shared_task
def expire_and_remind_subscriptions():
    """Passe les abonnements échus à "expired" et envoie les rappels "expire bientôt".

    Idempotent : on ne notifie chaque abonnement qu'une seule fois (un rappel
    "expire bientôt" n'est envoyé que si aucune notification de ce type
    n'existe déjà pour lui). À exécuter quotidiennement via Celery Beat.
    """
    today = timezone.now().date()

    # Auto-expiration des abonnements actifs dont la date de fin est dépassée.
    for subscription in Subscription.objects.filter(
        status=Subscription.Status.ACTIVE, ends_at__lt=today
    ):
        subscription.status = Subscription.Status.EXPIRED
        subscription.save(update_fields=["status"])
        subscription.notify_expired()
        # Entitlement commission du vendeur synchronisé (spec §17-§18) :
        # au-delà de la période de grâce le vendeur ne reçoit plus de commande.
        from apps.commissions.services import sync_plan_from_subscription
        sync_plan_from_subscription(subscription)

    # Rappel unique "expire bientôt" dans la fenêtre des 3 prochains jours.
    soon_cutoff = today + timedelta(days=3)
    expiring_soon = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE, ends_at__gte=today, ends_at__lte=soon_cutoff
    )
    for subscription in expiring_soon:
        already_notified = Notification.objects.filter(
            metadata__subscription_id=str(subscription.id),
            subject__icontains="expire bientôt",
        ).exists()
        if not already_notified:
            subscription.notify_expiring_soon((subscription.ends_at - today).days)
