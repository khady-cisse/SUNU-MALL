from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from .models import Report, TrafficStatistic, SalesStatistic
from .serializers import ReportSerializer, TrafficStatisticSerializer, SalesStatisticSerializer
from apps.catalog.models import Review, Store
from apps.orders.models import Order



class ReportViewSet(viewsets.ReadOnlyModelViewSet):
    """Rapports générés (ventes, trafic, inventaire) : chacun voit ses propres rapports, l'admin voit tout."""
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin():
            return Report.objects.all()
        return Report.objects.filter(generated_by=user)


class TrafficStatisticViewSet(viewsets.ReadOnlyModelViewSet):
    """Statistiques de trafic par boutique : le commerçant voit celles de ses boutiques, l'admin voit tout."""
    serializer_class = TrafficStatisticSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin():
            return TrafficStatistic.objects.all()
        return TrafficStatistic.objects.filter(store__owner=user)


class SalesStatisticViewSet(viewsets.ReadOnlyModelViewSet):
    """Statistiques de ventes par boutique : le commerçant voit celles de ses boutiques, l'admin voit tout."""
    serializer_class = SalesStatisticSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["store"]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        if user.is_admin():
            return SalesStatistic.objects.all()
        return SalesStatistic.objects.filter(store__owner=user)


class StoreSummaryView(APIView):
    """
    GET /api/analytics/store-summary/?store=<id>
    Résumé chiffré (30 derniers jours) pour le tableau de bord analytics
    d'un commerçant : chiffre d'affaires, commandes, panier moyen, taux de
    livraison et note moyenne — uniquement des agrégats calculés sur des
    données réelles (aucune métrique de trafic : TrafficStatistic n'est
    jamais alimenté dans ce projet, donc jamais exposé ici).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        store = get_object_or_404(Store, pk=request.query_params.get("store"))
        if store.owner_id != request.user.id and not request.user.is_admin():
            raise PermissionDenied("Vous ne pouvez consulter que les statistiques de votre propre boutique.")

        since = timezone.now() - timedelta(days=30)
        orders = Order.objects.filter(store=store, created_at__gte=since).exclude(status=Order.Status.CANCELLED)
        aggregate = orders.aggregate(revenue=Sum("total_amount"), count=Count("id"))
        revenue = aggregate["revenue"] or Decimal("0")
        order_count = aggregate["count"] or 0
        avg_order_value = (revenue / order_count) if order_count else Decimal("0")
        delivered_count = orders.filter(status=Order.Status.DELIVERED).count()
        delivered_rate = round((delivered_count / order_count) * 100, 1) if order_count else 0

        review_stats = Review.objects.filter(product__store=store).aggregate(avg=Avg("rating"), count=Count("id"))

        return Response(
            {
                "revenue_30d": str(revenue),
                "orders_30d": order_count,
                "avg_order_value_30d": str(avg_order_value),
                "delivered_rate": delivered_rate,
                "avg_rating": round(review_stats["avg"], 1) if review_stats["avg"] else None,
                "review_count": review_stats["count"],
            }
        )
