"""
Moteur de commission SUNU MALL (spec §1-§33).

Point d'entrée unique pour :
- figer le taux et ventiler une vente au moment du paiement confirmé (§8) ;
- contre-passer commission + fonds vendeur lors d'un remboursement (§20-§21) ;
- libérer les fonds en attente (pending → available) après la période de
  libération configurée (tâche Celery, §9) ;
- accepter/refuser un retrait du solde disponible (KYC vérifié, §19) ;
- synchroniser l'entitlement commission du vendeur depuis l'abonnement payé.

Toutes les écritures d'une opération sont dans transaction.atomic() ; la
contrainte unique (order, seller) + le garde-fou du paiement déjà marqué
succès rendent chaque traitement idempotent (webhook joué deux fois = un seul
crédit, §27-§28).
"""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.kyc.utils import seller_kyc_verified
from apps.monetization.models import Subscription
from apps.orders.models import Delivery
from apps.users.models import Role

from .models import (
    CommissionTransaction,
    Payout,
    PlatformTransaction,
    PlatformWallet,
    SellerSubscription,
    SellerWallet,
    WalletTransaction,
)

MONEY = Decimal("0.01")


def _money(value):
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- plans / gating

def get_or_create_seller_subscription(seller):
    return SellerSubscription.get_or_create_for(seller)


def can_receive_orders(seller, at=None):
    """Un vendeur sans essai ni plan actif, hors période de grâce ou suspendu,
    ne reçoit plus de commande (spec monétisation §11).

    Vérifie aussi le gating KYC (spec §8, §21) : une identité non vérifiée,
    suspendue ou bloquée coupe immédiatement la capacité à recevoir des
    commandes — indépendamment de l'abonnement payé.
    """
    if seller.is_admin():
        return True
    if not seller_kyc_verified(seller):
        return False
    # Abonnement monetization suspendu par un admin → coupe immédiatement la
    # vente, même si l'entitlement n'a pas encore été synchronisé.
    if Subscription.objects.filter(
        subscriber_type="merchant", subscriber_id=seller.id,
        status=Subscription.Status.SUSPENDED,
    ).exists():
        return False
    subscription = SellerSubscription.get_or_create_for(seller)
    return subscription.entitlement(at)["allowed"]


def sync_plan_from_subscription(monet_subscription):
    """Répercute l'abonnement SUNU MALL payé sur l'entitlement commission du vendeur.

    Appelée quand un abonnement devient ACTIVE (paiement confirmé) ou passe
    EXPIRED/CANCELLED (tâche Celery / action d'annulation).
    """
    if monet_subscription.subscriber_type != "merchant":
        return
    seller = monet_subscription.subscriber_user()
    if not seller:
        return
    entitlement = SellerSubscription.get_or_create_for(seller)

    if monet_subscription.status == Subscription.Status.ACTIVE:
        starts = timezone.make_aware(
            timezone.datetime.combine(monet_subscription.starts_at, timezone.datetime.min.time())
        )
        ends = timezone.make_aware(
            timezone.datetime.combine(monet_subscription.ends_at, timezone.datetime.max.time())
        )
        entitlement.apply_paid_plan(monet_subscription.plan.name, starts, ends)
    elif monet_subscription.status == Subscription.Status.EXPIRED:
        entitlement.mark_expired()
    elif monet_subscription.status == Subscription.Status.CANCELLED:
        entitlement.mark_cancelled()
    elif monet_subscription.status == Subscription.Status.SUSPENDED:
        entitlement.mark_suspended()


def _resolve(seller, at=None):
    subscription = SellerSubscription.get_or_create_for(seller)
    return subscription, subscription.entitlement(at)


# ------------------------------------------------------------------ vente (§6-§8)

def settle_commission_for_order(order):
    """Ventile une commande payée entre le vendeur et la plateforme.

    Idempotent : si la vente est déjà ventilée (unique order+seller), on
    renvoie l'enregistrement existant sans rien réécrire — un webhook joué
    deux fois ne crédite jamais deux fois.
    """
    seller = order.store.owner
    with transaction.atomic():
        existing = CommissionTransaction.objects.filter(order=order, seller=seller).first()
        if existing:
            return existing

        subscription, entitlement = _resolve(seller)
        rate = entitlement["rate"]
        plan_label = entitlement["plan"]

        # Montant éligible : le prix des produits (hors frais de livraison,
        # qui restent intégralement au vendeur). Le gross n'est jamais accepté
        # depuis le client — il est redérivé des lignes en base (§7).
        gross = order.total_amount - order.delivery_fee
        commission = _money(gross * rate / Decimal("100"))
        seller_amount = _money(gross - commission + order.delivery_fee)

        commission_tx = CommissionTransaction.objects.create(
            order=order, seller=seller, plan=plan_label,
            gross_amount=_money(gross), commission_rate=rate,
            commission_amount=commission, seller_amount=seller_amount,
        )

        wallet = SellerWallet.get_or_create_for(seller)
        available_before, pending_before = wallet.available_balance, wallet.pending_balance
        wallet.pending_balance = pending_before + seller_amount
        wallet.total_earned = wallet.total_earned + seller_amount
        wallet.save()
        WalletTransaction.objects.create(
            wallet=wallet, type=WalletTransaction.Type.SALE, amount=seller_amount,
            available_before=available_before, available_after=wallet.available_balance,
            pending_before=pending_before, pending_after=wallet.pending_balance,
            reference=f"order:{order.id}", order=order,
            description=f"Vente {order.total_amount} FCFA - commission {commission} FCFA",
        )

        platform = PlatformWallet.singleton()
        platform.balance = platform.balance + commission
        platform.total_commissions = platform.total_commissions + commission
        platform.save()
        PlatformTransaction.objects.create(
            wallet=platform, type=PlatformTransaction.Type.COMMISSION,
            amount=commission, reference=f"order:{order.id}", order=order,
            description=f"Commission {rate}% sur commande {str(order.id)[:8]}",
        )
        return commission_tx


# ------------------------------------------------------------------ abonnement

def register_subscription_revenue(subscription, amount):
    """Trace le revenu plateforme d'un abonnement payé (spec §22)."""
    with transaction.atomic():
        platform = PlatformWallet.singleton()
        platform.balance = platform.balance + amount
        platform.total_subscriptions = platform.total_subscriptions + amount
        platform.save()
        PlatformTransaction.objects.create(
            wallet=platform, type=PlatformTransaction.Type.SUBSCRIPTION,
            amount=amount, reference=f"subscription:{subscription.id}",
            description=f"Abonnement « {subscription.plan.name} » de {amount} FCFA",
        )


# ------------------------------------------------------------------ remboursement (§20-§21)

def reverse_commission_for_refund(refund):
    """Contre-passe la vente d'un remboursement traité.

    Le vendeur doit rendre le montant net déjà crédité ; la plateforme rend sa
    commission. Si le vendeur a déjà retiré les fonds, `available_balance`
    devient négatif (dette du vendeur, §21). Toujours en une transaction et
    protégé par le flag is_refunded.
    """
    order = refund.payment.order
    if order is None:
        return

    with transaction.atomic():
        commission_tx = CommissionTransaction.objects.filter(
            order=order, is_refunded=False
        ).first()
        if not commission_tx:
            return

        wallet = SellerWallet.get_or_create_for(commission_tx.seller)
        amount = commission_tx.seller_amount
        available_before, pending_before = wallet.available_balance, wallet.pending_balance

        takable_available = min(available_before, amount)
        remaining = amount - takable_available
        takable_pending = min(pending_before, remaining)
        deficit = remaining - takable_pending  # dette vendeur (§21) : solde dispo négatif

        wallet.available_balance = available_before - takable_available - deficit
        wallet.pending_balance = pending_before - takable_pending
        wallet.total_earned = max(Decimal("0"), wallet.total_earned - amount)
        wallet.save()

        WalletTransaction.objects.create(
            wallet=wallet, type=WalletTransaction.Type.REFUND, amount=-amount,
            available_before=available_before, available_after=wallet.available_balance,
            pending_before=pending_before, pending_after=wallet.pending_balance,
            reference=f"refund:{refund.id}", order=order,
            description=f"Remboursement {refund.amount} FCFA de la commande {str(order.id)[:8]}",
        )

        commission_tx.is_refunded = True
        commission_tx.refunded_at = timezone.now()
        commission_tx.save(update_fields=["is_refunded", "refunded_at"])

        platform = PlatformWallet.singleton()
        platform.balance = platform.balance - commission_tx.commission_amount
        platform.total_commissions = max(Decimal("0"), platform.total_commissions - commission_tx.commission_amount)
        platform.total_refunds = platform.total_refunds + commission_tx.commission_amount
        platform.save()
        PlatformTransaction.objects.create(
            wallet=platform, type=PlatformTransaction.Type.REFUND,
            amount=-commission_tx.commission_amount, reference=f"refund:{refund.id}",
            order=order,
            description=f"Rêversement de la commission {commission_tx.commission_rate}%",
        )


# ------------------------------------------------------------------ libération (pending → available)

def release_pending_funds(at=None, seller=None):
    """Livre aux vendeurs les fonds des ventes livrées depuis COMMISSION_RELEASE_DAYS.

    Idempotent via le flag is_released de chaque vente ventilée. Exécuté
    quotidiennement par Celery Beat (tâche apps.commissions.tasks.release_pending_funds).
    """
    at = at or timezone.now()
    cutoff = at - timedelta(days=settings.COMMISSION_RELEASE_DAYS)

    qs = CommissionTransaction.objects.filter(
        is_refunded=False, is_released=False,
        order__delivery__status=Delivery.Status.DELIVERED,
        order__delivery__delivered_at__lte=cutoff,
    ).select_related("seller__seller_wallet")
    if seller:
        qs = qs.filter(seller=seller)

    released = 0
    for commission_tx in qs:
        with transaction.atomic():
            # Relu sous verrou de ligne : deux tâches concurrentes ne libèrent qu'une fois.
            current = CommissionTransaction.objects.select_for_update().get(pk=commission_tx.pk)
            if current.is_released:
                continue
            wallet = SellerWallet.objects.select_for_update().get(pk=current.seller.seller_wallet.pk)
            pending_before = wallet.pending_balance
            moving = current.seller_amount
            wallet.pending_balance = pending_before - moving
            wallet.available_balance = wallet.available_balance + moving
            wallet.save()
            WalletTransaction.objects.create(
                wallet=wallet, type=WalletTransaction.Type.RELEASE, amount=moving,
                available_before=wallet.available_balance - moving,
                available_after=wallet.available_balance,
                pending_before=pending_before, pending_after=wallet.pending_balance,
                reference=f"release:{current.id}", order=current.order,
                description="Libération des fonds de vente livrée",
            )
            current.is_released = True
            current.released_at = at
            current.save(update_fields=["is_released", "released_at"])
            released += 1
    return released


# ------------------------------------------------------------------ retrait (§19)

class PayoutError(Exception):
    pass


def request_payout(seller, amount, method="wave"):
    """Crée un retrait depuis le solde disponible (jamais les fonds en attente).

    Conditions (spec §19) : KYC vendeur vérifié + compte actif + solde
    disponible suffisant. Le débit est immédiat et tracé ; l'argent part
    réellement quand l'admin marque le retrait complété.
    """
    if amount <= 0:
        raise PayoutError("Le montant du retrait doit être positif.")
    if not seller_kyc_verified(seller):
        raise PayoutError(
            "Votre identité (KYC) doit être vérifiée par un administrateur avant de pouvoir retirer vos fonds."
        )
    entitlement = SellerSubscription.get_or_create_for(seller)
    if not entitlement.entitlement()["allowed"]:
        raise PayoutError("Votre abonnement ne vous permet pas encore de retirer vos fonds.")

    with transaction.atomic():
        SellerWallet.objects.get_or_create(seller=seller)
        wallet = SellerWallet.objects.select_for_update().get(seller=seller)
        if wallet.available_balance < amount:
            raise PayoutError(
                f"Solde disponible insuffisant : {wallet.available_balance} FCFA."
            )
        available_before = wallet.available_balance
        wallet.available_balance = available_before - amount
        wallet.total_withdrawn = wallet.total_withdrawn + amount
        wallet.save()

        payout = Payout.objects.create(seller=seller, amount=amount, method=method)
        WalletTransaction.objects.create(
            wallet=wallet, type=WalletTransaction.Type.PAYOUT, amount=-amount,
            available_before=available_before, available_after=wallet.available_balance,
            pending_before=wallet.pending_balance, pending_after=wallet.pending_balance,
            reference=f"payout:{payout.id}",
            description=f"Retrait de {amount} FCFA demandé (Wave/Orange Money)",
        )
        return payout


def complete_payout(payout, approved):
    """Marque un retrait complété (les fonds ont été transférés) ou rejeté.

    En cas de rejet, le montant est crédité de nouveau sur le solde disponible.
    """
    with transaction.atomic():
        current = Payout.objects.select_for_update().get(pk=payout.pk)
        if current.status != Payout.Status.PENDING:
            raise PayoutError("Ce retrait a déjà été traité.")
        if not approved:
            SellerWallet.objects.get_or_create(seller=current.seller)
            wallet = SellerWallet.objects.select_for_update().get(seller=current.seller)
            available_before = wallet.available_balance
            wallet.available_balance = available_before + current.amount
            wallet.total_withdrawn = max(Decimal("0"), wallet.total_withdrawn - current.amount)
            wallet.save()
            WalletTransaction.objects.create(
                wallet=wallet, type=WalletTransaction.Type.ADJUSTMENT, amount=current.amount,
                available_before=available_before, available_after=wallet.available_balance,
                pending_before=wallet.pending_balance, pending_after=wallet.pending_balance,
                reference=f"payout-reject:{current.id}",
                description=f"Retrait {current.amount} FCFA rejeté — recrédité",
            )
            current.status = Payout.Status.REJECTED
        else:
            current.status = Payout.Status.COMPLETED
            platform = PlatformWallet.singleton()
            platform.balance = platform.balance - current.amount
            platform.total_payouts = platform.total_payouts + current.amount
            platform.save()
            PlatformTransaction.objects.create(
                wallet=platform, type=PlatformTransaction.Type.PAYOUT,
                amount=-current.amount, reference=f"payout:{current.id}",
                description=f"Retrait {current.amount} FCFA vers le vendeur {current.seller_id}",
            )
        current.reference = current.reference or f"PO-{current.id}"
        current.completed_at = timezone.now()
        current.save(update_fields=["status", "reference", "completed_at"])


# ------------------------------------------------------------------ résumé vendeur (dashboard)

def seller_summary(seller):
    """Portefeuille + entitlement + ventes récentes pour le dashboard vendeur."""
    subscription = SellerSubscription.get_or_create_for(seller)
    entitlement = subscription.entitlement()
    wallet = SellerWallet.get_or_create_for(seller)
    return {
        "wallet": wallet,
        "subscription": {
            "status": subscription.effective_status,
            "plan": subscription.plan,
            "trial_ends_at": subscription.trial_ends_at,
            "starts_at": subscription.starts_at,
            "ends_at": subscription.ends_at,
            "rate": f"{entitlement['rate']:.2f}",
            "can_sell": entitlement["allowed"],
        },
        "recent_sales": (
            CommissionTransaction.objects.filter(seller=seller)
            .select_related("order__store")
            .order_by("-created_at")[:10]
        ),
    }