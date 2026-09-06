from datetime import timedelta

from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from .models import Notification, SponsoredProduct, SubscriptionPlan, Subscription, Invoice
from .serializers import (
    NotificationSerializer, SponsoredProductSerializer,
    SubscriptionPlanSerializer, SubscriptionSerializer, InvoiceSerializer,
)
from apps.users.permissions import IsAdmin
from apps.users.models import Role

# Durée d'une période d'abonnement selon le cycle de facturation du plan —
# utilisé pour calculer starts_at/ends_at côté serveur (jamais fourni par le
# client, contrairement à l'ancien comportement qui exigeait ces dates dans
# la requête et échouait systématiquement en pratique).
BILLING_CYCLE_DAYS = {"monthly": 30, "yearly": 365}


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """Un utilisateur ne voit que ses propres notifications (créées par le système)."""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    """Offres BASIC/PRO/BUSINESS : lecture publique des plans actifs, gestion réservée à l'admin."""
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [permissions.IsAuthenticated(), IsAdmin()]
        return super().get_permissions()

    def get_queryset(self):
        # Un plan désactivé (is_active=False) n'est plus proposé (spec §16) :
        # seuls l'admin et le Swagger le voient encore.
        user = self.request.user
        if user is not None and user.is_authenticated and user.has_role(Role.RoleName.ADMIN):
            return self.queryset
        return self.queryset.filter(is_active=True)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def subscribe(self, request, pk=None):
        """
        POST /api/monetization/subscription-plans/{id}/subscribe/
        Crée l'abonnement (en attente) et son paiement associé pour le
        commerçant connecté — les dates et le statut sont calculés côté
        serveur, jamais fournis par le client. Une offre gratuite (price=0)
        est activée immédiatement, sans paiement à confirmer. Pour une offre
        payante, le paiement renvoyé se confirme ensuite via l'action
        sandbox-confirm déjà utilisée pour les commandes.
        """
        from apps.payments.models import Payment
        from apps.payments.serializers import PaymentSerializer

        plan = self.get_object()
        if not plan.is_active:
            raise PermissionDenied("Cette offre n'est plus disponible.")
        user = request.user
        if not user.has_role(Role.RoleName.MERCHANT):
            raise PermissionDenied("Réservé aux comptes commerçants.")

        if Subscription.objects.filter(
            subscriber_id=user.id, subscriber_type="merchant", status=Subscription.Status.ACTIVE
        ).exists():
            return Response(
                {"error": "Vous avez déjà un abonnement actif. Annulez-le avant d'en choisir un autre."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.now().date()
        days = plan.duration_days or BILLING_CYCLE_DAYS.get(plan.billing_cycle, 30)
        subscription = Subscription.objects.create(
            plan=plan, subscriber_type="merchant", subscriber_id=user.id,
            starts_at=today, ends_at=today + timedelta(days=days),
        )

        if plan.price <= 0:
            subscription.status = Subscription.Status.ACTIVE
            subscription.save(update_fields=["status"])
            from apps.commissions.services import sync_plan_from_subscription
            sync_plan_from_subscription(subscription)
            return Response(
                {"subscription": SubscriptionSerializer(subscription).data, "payment": None},
                status=status.HTTP_201_CREATED,
            )

        payment = Payment.objects.create(
            subscription=subscription, amount=plan.price,
            method=request.data.get("payment_method", "wave"),
        )
        return Response(
            {"subscription": SubscriptionSerializer(subscription).data, "payment": PaymentSerializer(payment).data},
            status=status.HTTP_201_CREATED,
        )


class SubscriptionViewSet(viewsets.ModelViewSet):
    """Un commerçant gère ses propres abonnements (via l'action `subscribe` du plan, pas en écrivant ici) ; l'admin voit et gère tout."""
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Fenêtre du rappel "expire bientôt" avant la date de fin.
    EXPIRING_SOON_DAYS = 3

    def get_queryset(self):
        # Note : l'expiration et les rappels sont traités en tâche Celery
        # périodique (apps.monetization.tasks.expire_and_remind_subscriptions),
        # plus dans cette lecture — un simple GET ne fait plus d'écriture ni
        # d'envoi d'email (voir CELERY_BEAT_SCHEDULE dans settings).
        user = self.request.user
        if user.has_role(Role.RoleName.ADMIN):
            return Subscription.objects.all()
        return Subscription.objects.filter(subscriber_id=user.id)

    def perform_create(self, serializer):
        # Réservé à l'admin (cas d'exception : accorder un abonnement
        # manuellement) — un commerçant passe toujours par l'action
        # `subscribe` du plan, qui calcule dates/statut correctement.
        if not self.request.user.has_role(Role.RoleName.ADMIN):
            raise PermissionDenied("Utilisez l'action « subscribe » d'une offre pour vous abonner.")
        serializer.save()

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        subscription = self.get_object()
        subscription.cancel()
        # Répercute l'annulation sur l'entitlement commission du vendeur
        # (spec §16-§18) : au-delà de la période de grâce il ne reçoit plus
        # de nouvelles commandes. Sans ça, un plan annulé restait appliqué.
        from apps.commissions.services import sync_plan_from_subscription
        sync_plan_from_subscription(subscription)
        return Response(self.get_serializer(subscription).data, status=status.HTTP_200_OK)


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    """Factures liées aux abonnements du commerçant connecté ; l'admin voit tout."""
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.has_role(Role.RoleName.ADMIN):
            return Invoice.objects.all()
        return Invoice.objects.filter(subscription__subscriber_id=user.id)


class SponsoredProductViewSet(viewsets.ModelViewSet):
    """Un commerçant gère la mise en avant de ses propres produits ; l'admin voit et gère tout."""
    serializer_class = SponsoredProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.has_role(Role.RoleName.ADMIN):
            return SponsoredProduct.objects.all()
        return SponsoredProduct.objects.filter(store__owner=user)

    def perform_create(self, serializer):
        user = self.request.user
        store = serializer.validated_data.get("store")
        if not user.has_role(Role.RoleName.ADMIN) and store.owner_id != user.id:
            raise PermissionDenied("Vous ne pouvez sponsoriser que les produits de votre propre boutique.")
        serializer.save()
