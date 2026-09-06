from decimal import Decimal

from django.db import models as db_models
from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.users.models import Role
from apps.users.permissions import IsAdmin

from .models import CommissionTransaction, Payout, SellerWallet, WalletTransaction
from .serializers import (
    CommissionTransactionSerializer, PayoutSerializer, WalletSerializer, WalletTransactionSerializer,
)
from . import services


class SellerSubscriptionViewSet(viewsets.ViewSet):
    """Entitlement commission du vendeur : essai, plan actif, taux et gating.

    Le endpoint `me` (GET) est le point d'entrée unique pour la page
    portefeuille du vendeur : il regroupe le statut de l'abonnement (essai
    restant, plan, taux), les soldes du portefeuille et les dernières ventes.
    Les plans disponibles pour souscrire sont lus via l'endpoint existant
    `monetization/subscription-plans/`.
    """
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        user = request.user
        if not user.has_role(Role.RoleName.MERCHANT):
            raise PermissionDenied("Réservé aux comptes commerçants.")
        return Response(_seller_dashboard(user))


class SellerWalletViewSet(viewsets.ViewSet):
    """Portefeuille du vendeur (solde, historicaliques, action de release)."""
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        user = request.user
        if not user.has_role(Role.RoleName.MERCHANT):
            raise PermissionDenied("Réservé aux comptes commerçants.")
        return Response(_seller_dashboard(user))

    @action(detail=False, methods=["post"], url_path="release", permission_classes=[permissions.IsAuthenticated, IsAdmin])
    def release(self, request):
        """Déclenche la libération manuelle des fonds (admin / démo / tâche Celery)."""
        released = services.release_pending_funds()
        return Response({"released": released})


class CommissionTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """Journal des ventes ventilées par vendeur.

    - admin : tout le journal, avec filtres (seller, plan, date_from, date_to)
    - commerçant : ses propres ventes uniquement

    Le statut `is_released` indique si les fonds de la vente ont été
    libérés (pending → available) après la période de libération.
    """
    serializer_class = CommissionTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = CommissionTransaction.objects.select_related("order__store", "order__customer")
        if not user.has_role(Role.RoleName.ADMIN):
            qs = qs.filter(seller=user)
            return qs
        params = self.request.query_params
        seller = params.get("seller")
        if seller:
            qs = qs.filter(seller_id=seller)
        plan = params.get("plan")
        if plan:
            # Les ventes réalisées pendant l'essai gratuite sont stockées avec
            # un plan vide ("" — voir models.SellerSubscription.resolve_rate) :
            # le filtre admin « Essai (trial) » les cible explicitement.
            qs = qs.filter(plan="" if plan == "trial" else plan)
        date_from = params.get("date_from")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = params.get("date_to")
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs

    @action(detail=False, methods=["get"], url_path="stats", permission_classes=[permissions.IsAuthenticated, IsAdmin])
    def stats(self, request):
        """Statistiques de commissions (§25) : totaux, aujourd'hui, mois, par plan."""
        from django.utils import timezone
        from django.db.models import Sum, Count
        from .models import PlatformWallet

        today = timezone.now().date()
        month_start = today.replace(day=1)

        base = self.get_queryset()
        not_refunded = base.filter(is_refunded=False)

        totals = not_refunded.aggregate(
            total_volume=db_models.Sum("gross_amount"),
            total_commissions=db_models.Sum("commission_amount"),
            total_to_sellers=db_models.Sum("seller_amount"),
        )

        today_qs = not_refunded.filter(created_at__date=today)
        month_qs = not_refunded.filter(created_at__date__gte=month_start)

        by_plan = list(
            not_refunded.values("plan")
            .annotate(
                count=Count("id"),
                commissions=db_models.Sum("commission_amount"),
                volume=db_models.Sum("gross_amount"),
            )
            .order_by("plan")
        )

        # Remboursements totaux (tous status REFINDED sur CommissionTransaction)
        refunded = base.filter(is_refunded=True)
        refunded_commissions = refunded.aggregate(s=db_models.Sum("commission_amount"))["s"] or Decimal("0")

        payout_total = Payout.objects.filter(status=Payout.Status.COMPLETED).aggregate(
            s=db_models.Sum("amount")
        )["s"] or Decimal("0")

        platform = PlatformWallet.singleton()

        def money(value):
            return f"{value:.2f}"

        return Response({
            "today_commissions": money(today_qs.aggregate(s=db_models.Sum("commission_amount"))["s"] or Decimal("0")),
            "month_commissions": money(month_qs.aggregate(s=db_models.Sum("commission_amount"))["s"] or Decimal("0")),
            "total_commissions": money(totals["total_commissions"] or Decimal("0")),
            "total_volume": money(totals["total_volume"] or Decimal("0")),
            "total_to_sellers": money(totals["total_to_sellers"] or Decimal("0")),
            "total_refunded_commissions": money(refunded_commissions),
            "total_payouts": money(payout_total),
            "platform_balance": money(platform.balance),
            "platform_total_subscriptions": money(platform.total_subscriptions),
            "by_plan": [
                {
                    "plan": p["plan"],
                    "count": p["count"],
                    "commissions": money(p["commissions"] or Decimal("0")),
                    "volume": money(p["volume"] or Decimal("0")),
                }
                for p in by_plan
            ],
        })


def _seller_dashboard(user):
    summary = services.seller_summary(user)
    wallet = summary["wallet"]
    recent_sales = CommissionTransactionSerializer(summary["recent_sales"], many=True).data
    recent_tx = WalletTransactionSerializer(
        WalletTransaction.objects.filter(wallet=wallet)[:10], many=True
    ).data
    return {
        "wallet": WalletSerializer(wallet).data,
        "subscription": summary["subscription"],
        "recent_sales": recent_sales,
        "recent_wallet_transactions": recent_tx,
    }


class PayoutViewSet(viewsets.ModelViewSet):
    """Demandes de retrait (vendeur : créer ; admin : approuver / rejeter)."""
    serializer_class = PayoutSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.has_role(Role.RoleName.ADMIN):
            return Payout.objects.all()
        return Payout.objects.filter(seller=user)

    def perform_create(self, serializer):
        user = self.request.user
        if not user.has_role(Role.RoleName.MERCHANT):
            raise PermissionDenied("Seuls les commerçants peuvent demander un retrait.")
        amount = serializer.validated_data.get("amount")
        method = serializer.validated_data.get("method", "wave")
        try:
            payout = services.request_payout(user, amount, method)
        except services.PayoutError as exc:
            raise ValidationError(str(exc))
        serializer.instance = payout

    @action(detail=True, methods=["post"], url_path="approve", permission_classes=[permissions.IsAuthenticated, IsAdmin])
    def approve(self, request, pk=None):
        payout = self.get_object()
        try:
            services.complete_payout(payout, approved=True)
        except services.PayoutError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payout.refresh_from_db()
        return Response(PayoutSerializer(payout).data)

    @action(detail=True, methods=["post"], url_path="reject", permission_classes=[permissions.IsAuthenticated, IsAdmin])
    def reject(self, request, pk=None):
        payout = self.get_object()
        try:
            services.complete_payout(payout, approved=False)
        except services.PayoutError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payout.refresh_from_db()
        return Response(PayoutSerializer(payout).data)