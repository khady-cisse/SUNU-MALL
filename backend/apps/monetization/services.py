"""
Services abonnements SUNU MALL (spec monétisation).

Centralise la lecture de l'état d'abonnement d'un vendeur et le calcul de la
limite de produits appliquée sur le catalogue — le backend est la seule source
de vérité, le frontend n'est jamais autorisé à décider d'un statut ni d'une
limite.
"""
from django.conf import settings
from django.utils import timezone

from apps.users.models import Role

from .models import Subscription, SubscriptionPlan


PRODUCT_LIMIT_EXCEEDED_MESSAGE = (
    "Vous avez atteint la limite de produits de votre abonnement. "
    "Passez à une formule supérieure pour ajouter davantage de produits."
)


def active_subscription(seller):
    """Abonnement monetization ACTIVE et dans sa fenêtre de validité — None sinon."""
    today = timezone.now().date()
    return (
        Subscription.objects.filter(
            subscriber_type="merchant", subscriber_id=seller.id,
            status=Subscription.Status.ACTIVE,
            starts_at__lte=today, ends_at__gte=today,
        )
        .select_related("plan")
        .order_by("-created_at")
        .first()
    )


def latest_subscription(seller):
    """Dernier abonnement du vendeur (tous statuts confondus) — None sinon."""
    return (
        Subscription.objects.filter(subscriber_type="merchant", subscriber_id=seller.id)
        .select_related("plan")
        .order_by("-created_at")
        .first()
    )


def _entry_plan():
    """L'offre d'entrée (moins chère) sert de plafond par défaut."""
    return SubscriptionPlan.objects.filter(is_active=True).order_by("price", "id").first()


def product_limit_for(seller):
    """Limite de produits du vendeur : None = illimité, 0 = bloqué.

    Règles (spec §10-§11, §24) :
    - abonnement actif → limite de sa formule (None = illimité) ;
    - essai 0 % en cours ou période de grâce → plafond de l'offre d'entrée
      (ou de la dernière formule payée pendant la grâce) ;
    - retrait/annulation/hors grâce → bloqué (0).
    """
    if seller.is_admin():
        return None
    sub = active_subscription(seller)
    if sub:
        return sub.plan.max_products

    from apps.commissions.models import SellerSubscription

    entitlement = SellerSubscription.get_or_create_for(seller)
    now = timezone.now()

    if entitlement.status == entitlement.Status.CANCELLED:
        return 0
    if entitlement.status == entitlement.Status.SUSPENDED:
        return 0
    if entitlement.trial_active(now):
        plan = _entry_plan()
        return plan.max_products if plan else None
    if entitlement.in_grace(now):
        plan = entitlement.plan_obj() or _entry_plan()
        return plan.max_products if plan else None
    return 0


def _product_count_for_seller(seller):
    from apps.catalog.models import Product

    store_ids = seller.stores.values_list("id", flat=True)
    return Product.objects.filter(store_id__in=store_ids).count()


def check_product_creation_allowed(seller):
    """Lève une ValidationError si le vendeur ne peut plus créer de produit."""
    from rest_framework.exceptions import ValidationError

    limit = product_limit_for(seller)
    if limit is None:
        return
    if limit == 0:
        raise ValidationError(
            "Vous n'avez pas d'abonnement actif. Souscrivez à une formule pour créer des produits."
        )
    if _product_count_for_seller(seller) >= limit:
        raise ValidationError(PRODUCT_LIMIT_EXCEEDED_MESSAGE)


def subscription_state(seller):
    """État complet pour la page « Mon abonnement » du vendeur."""
    sub = latest_subscription(seller)
    active = active_subscription(seller)
    limit = product_limit_for(seller)
    count = _product_count_for_seller(seller)

    if sub is None:
        current = None
    else:
        current = {
            "id": sub.id,
            "status": sub.status,
            "plan_code": sub.plan.code,
            "plan_name": sub.plan.name,
            "starts_at": sub.starts_at,
            "ends_at": sub.ends_at,
            "days_left": sub.days_left if sub.status == Subscription.Status.ACTIVE else 0,
            "is_active": sub.is_active(),
            "in_grace": sub.in_grace(),
            "price": f"{sub.plan.price:.2f}",
            "billing_cycle": sub.plan.billing_cycle,
        }

    return {
        "subscription": current,
        "has_active_subscription": active is not None,
        "product_limit": limit,
        "product_count": count,
        "products_remaining": None if limit is None else max(0, limit - count),
        "is_unlimited": limit is None,
        "grace_period_days": settings.SUBSCRIPTION_GRACE_PERIOD_DAYS,
    }


def has_subscription_history(user):
    """Vrai si le vendeur a déjà eu au moins un abonnement — n'importe quel
    statut (actif, expiré, annulé…). Sert à n'accorder le premier mois
    gratuit (spec §31) qu'à la toute première souscription du vendeur."""
    return Subscription.objects.filter(
        subscriber_type="merchant", subscriber_id=user.id,
    ).exists()


def seed_default_plans():
    """Seed idempotent des trois formules (tests `--nomigrations` et premières bases).

    Codes stables STARTER / PRO / BUSINESS ; commission SUNU MALL à 0 %.
    Limites produits conformes à la spec : Starter 10 / Pro 30 / Business illimité.
    """
    default_plans = [
        {
            "code": "STARTER", "name": "STARTER", "price": 2500,
            "billing_cycle": "monthly", "duration_days": 30,
            "max_products": 10, "commission_rate": "0.00",
            "features": {
                "produits": "10 produits",
                "paiements": "Paiements client et livraison inclus",
                "support": "Support standard",
            },
        },
        {
            "code": "PRO", "name": "PRO", "price": 5000,
            "billing_cycle": "monthly", "duration_days": 30,
            "max_products": 30, "commission_rate": "0.00",
            "features": {
                "produits": "30 produits",
                "paiements": "Paiements client et livraison inclus",
                "support": "Support prioritaire",
            },
        },
        {
            "code": "BUSINESS", "name": "BUSINESS", "price": 10000,
            "billing_cycle": "monthly", "duration_days": 30,
            "max_products": None, "commission_rate": "0.00",
            "features": {
                "produits": "Produits illimités",
                "paiements": "Paiements client et livraison inclus",
                "support": "Support dédié",
            },
        },
    ]
    created = 0
    for data in default_plans:
        _, was_created = SubscriptionPlan.objects.update_or_create(
            code=data["code"],
            defaults={
                "name": data["name"],
                "price": data["price"],
                "billing_cycle": data["billing_cycle"],
                "duration_days": data["duration_days"],
                "max_products": data["max_products"],
                "commission_rate": data["commission_rate"],
                "features": data["features"],
                "is_active": True,
            },
        )
        created += int(was_created)
    return created