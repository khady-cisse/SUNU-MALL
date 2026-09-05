"""
Rapports et statistiques.
"""
import uuid
from django.db import models
from django.utils import timezone
from apps.users.models import User
from apps.catalog.models import Store


class Report(models.Model):
    class Type(models.TextChoices):
        SALES = 'sales', 'Sales'
        TRAFFIC = 'traffic', 'Traffic'
        INVENTORY = 'inventory', 'Inventory'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reports')
    type = models.CharField(max_length=50, choices=Type.choices)
    period_start = models.DateField()
    period_end = models.DateField()
    minio_path = models.CharField(max_length=255, blank=True)
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def get_download_url(self):
        return self.minio_path

    def __str__(self):
        return f"Report {self.id} - {self.type}"


class TrafficStatistic(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='traffic_stats')
    date = models.DateField()
    visits = models.IntegerField(default=0)
    unique_visitors = models.IntegerField(default=0)
    conversion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['store', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"Traffic {self.store.name} - {self.date}"


class SalesStatistic(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='sales_stats')
    date = models.DateField()
    total_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_orders = models.IntegerField(default=0)
    avg_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['store', 'date']
        ordering = ['-date']

    @staticmethod
    def compute_for_store(store, date):
        """
        Agrège les commandes réelles de la boutique pour le jour donné
        (toutes sauf annulées) et enregistre/actualise la ligne de stats
        du jour. Idempotent : peut être relancé sans dupliquer (upsert
        sur la contrainte unique store+date).
        """
        from decimal import Decimal
        from django.db.models import Count, Sum
        from apps.orders.models import Order

        aggregate = Order.objects.filter(
            store=store, created_at__date=date,
        ).exclude(status=Order.Status.CANCELLED).aggregate(
            total=Sum("total_amount"), count=Count("id"),
        )
        total_sales = aggregate["total"] or Decimal("0")
        total_orders = aggregate["count"] or 0
        avg_order_value = (total_sales / total_orders) if total_orders else Decimal("0")

        stat, _ = SalesStatistic.objects.update_or_create(
            store=store, date=date,
            defaults={
                "total_sales": total_sales,
                "total_orders": total_orders,
                "avg_order_value": avg_order_value,
            },
        )
        return stat

    def __str__(self):
        return f"Sales {self.store.name} - {self.date}"
