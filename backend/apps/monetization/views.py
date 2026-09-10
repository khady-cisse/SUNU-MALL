from datetime import timedelta

from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .models import Notification, SponsoredProduct, SubscriptionPlan, Subscription, SubscriptionHistory, Invoice
from .serializers import (
    NotificationSerializer, SponsoredProductSerializer,
    SubscriptionPlanSerializer, SubscriptionSerializer, SubscriptionHistorySerializer, InvoiceSerializer,
)
from . import services
from apps.users.permissions import IsAdmin
from apps.users.models import Role, User
from apps.security.utils import log_admin_event

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

    @action(detail=False, methods=["post"])
    def broadcast(self, request):
        """Diffusion d'une notification à tous les acteurs (ou à un rôle, spec admin)."""
        if not request.user.is_admin():
            raise PermissionDenied("Seul un administrateur peut diffuser une notification.")
        subject = request.data.get("subject", "").strip()
        message = request.data.get("message", "").strip()
        if not subject or not message:
            raise ValidationError("Les champs 'subject' et 'message' sont requis.")
        role_name = request.data.get("role") or None
        channel = request.data.get("channel", Notification.Channel.EMAIL)
        recipients = User.objects.filter(is_active=True)
        if role_name:
            recipients = recipients.filter(user_roles__role__name=role_name)
        total = 0
        for user in recipients.iterator():
            Notification.objects.create(user=user, channel=channel, subject=subject, message=message)
            total += 1
        log_admin_event(request.user, "other", request, object_type="Notification",
                        summary=f"Diffusion « {subject} » à {total} utilisateur(s) "
                                f"({'tous' if not role_name else role_name})")
        return Response({"sent": total, "role": role_name or "all"})


class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    """Offres STARTER/PRO/BUSINESS : lecture publique des plans actifs, gestion réservée à l'admin."""
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
        if user is not None and user.is_authenticated and user.is_admin():
            return self.queryset
        return self.queryset.filter(is_active=True)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def subscribe(self, request, pk=None):
        """
        POST /api/monetization/plans/{id}/subscribe/
        Crée l'abonnement (en attente) et son paiement associé pour le
        commerçant connecté — les dates et le statut sont calculés côté
        serveur, jamais fournis par le client. Une offre gratuite (price=0)
        est activée immédiatement, sans paiement à confirmer. Pour une offre
        payante, le paiement renvoyé se confirme ensuite via l'action
        sandbox-confirm ou un webhook fournisseur.
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
                {"error": "Vous avez déjà un abonnement actif. Renouvelez-le ou changez de formule."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if Subscription.objects.filter(
            subscriber_id=user.id, subscriber_type="merchant",
            status__in=[Subscription.Status.PENDING, Subscription.Status.SUSPENDED],
        ).exists():
            return Response(
                {"error": "Une demande d'abonnement est déjà en attente ou suspendue."},
                status=status.HTTP_409_CONFLICT,
            )

        today = timezone.now().date()
        days = plan.duration_days or BILLING_CYCLE_DAYS.get(plan.billing_cycle, 30)
        subscription = Subscription.objects.create(
            plan=plan, subscriber_type="merchant", subscriber_id=user.id,
            starts_at=today, ends_at=today + timedelta(days=days),
        )
        subscription.record_history(
            SubscriptionHistory.Action.CREATED, new_plan=plan,
            old_end_date=None, new_end_date=subscription.ends_at,
        )

        # Premier mois gratuit (spec §31) : la TOUTE première souscription du
        # vendeur est activée immédiatement, sans paiement, quel que soit le
        # prix de la formule. Les souscriptions suivantes (renouvellement,
        # resouscription après expiration) sont bien facturées.
        first_month_free = plan.price > 0 and not services.has_subscription_history(user)

        if plan.price <= 0 or first_month_free:
            subscription.status = Subscription.Status.ACTIVE
            subscription.save(update_fields=["status"])
            subscription.record_history(
                SubscriptionHistory.Action.ACTIVATED, old_plan=plan, new_plan=plan,
                old_end_date=None, new_end_date=subscription.ends_at,
                metadata={
                    "promo": "first_month_free" if first_month_free else "free_plan",
                    "regular_price": str(plan.price),
                },
            )
            from apps.commissions.services import sync_plan_from_subscription
            sync_plan_from_subscription(subscription)
            return Response(
                {
                    "subscription": SubscriptionSerializer(subscription).data,
                    "payment": None,
                    "promo": "first_month_free" if first_month_free else None,
                },
                status=status.HTTP_201_CREATED,
            )

        payment = Payment.objects.create(
            subscription=subscription, amount=plan.price, currency="XOF",
            method=request.data.get("payment_method", "wave"),
            metadata={"action": "subscribe"},
        )
        return Response(
            {"subscription": SubscriptionSerializer(subscription).data, "payment": PaymentSerializer(payment).data},
            status=status.HTTP_201_CREATED,
        )


def _require_merchant(user):
    if not user.has_role(Role.RoleName.MERCHANT):
        raise PermissionDenied("Réservé aux comptes commerçants.")


def _pending_payment_for(subscription):
    from apps.payments.models import Payment

    return Payment.objects.filter(
        subscription=subscription, status=Payment.Status.PENDING
    ).first()


class SubscriptionViewSet(viewsets.ModelViewSet):
    """Un commerçant gère ses propres abonnements (via l'action `subscribe` du plan) ; l'admin voit et gère tout."""
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Note : l'expiration et les rappels sont traités en tâche Celery
        # périodique (apps.monetization.tasks.expire_and_remind_subscriptions),
        # plus dans cette lecture — un simple GET ne fait plus d'écriture ni
        # d'envoi d'email (voir CELERY_BEAT_SCHEDULE dans settings).
        user = self.request.user
        if user.is_admin():
            return Subscription.objects.all()
        return Subscription.objects.filter(subscriber_id=user.id)

    def perform_create(self, serializer):
        # Réservé à l'admin (cas d'exception : accorder un abonnement
        # manuellement) — un commerçant passe toujours par l'action
        # `subscribe` du plan, qui calcule dates/statut correctement.
        if not self.request.user.is_admin():
            raise PermissionDenied("Utilisez l'action « subscribe » d'une offre pour vous abonner.")
        serializer.save()

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        """État complet « Mon abonnement » : formule, dates, limite produits."""
        _require_merchant(request.user)
        return Response(services.subscription_state(request.user))

    @action(detail=False, methods=["post"], url_path="renew")
    def renew(self, request):
        """
        POST /api/monetization/subscription/renew/
        Prépare le renouvellement de la formule courante : crée un paiement
        en attente (jamais d'activation directe). La période n'est allongée
        qu'après confirmation backend du paiement.
        """
        _require_merchant(request.user)
        subscription = services.latest_subscription(request.user)
        if subscription is None:
            return Response(
                {"error": "Aucun abonnement à renouveler. Souscrivez d'abord à une formule."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if subscription.status in (Subscription.Status.CANCELLED, Subscription.Status.SUSPENDED):
            return Response(
                {"error": "Cet abonnement ne peut pas être renouvelé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pending = _pending_payment_for(subscription)
        if pending:
            return Response(
                {"error": "Un paiement de renouvellement est déjà en attente.", "payment": pending.id},
                status=status.HTTP_409_CONFLICT,
            )

        from apps.payments.models import Payment
        from apps.payments.serializers import PaymentSerializer

        payment = Payment.objects.create(
            subscription=subscription, amount=subscription.plan.price, currency="XOF",
            method=request.data.get("payment_method", "wave"),
            metadata={"action": "renew"},
        )
        return Response({"payment": PaymentSerializer(payment).data}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="change-plan")
    def change_plan(self, request):
        """
        POST /api/monetization/subscription/change-plan/   {"plan_code": "PRO"}
        Monte/descend de formule : un paiement en attente est créé ; le
        changement n'est appliqué qu'après confirmation backend du paiement
        (l'historique garde l'ancienne et la nouvelle formule).
        """
        _require_merchant(request.user)
        plan_code = request.data.get("plan_code")
        plan = SubscriptionPlan.objects.filter(code=plan_code, is_active=True).first()
        if plan is None:
            return Response(
                {"error": "Formule inconnue ou indisponible."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        subscription = services.latest_subscription(request.user)
        if subscription is None:
            return Response(
                {"error": "Aucun abonnement à modifier."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if subscription.status == Subscription.Status.SUSPENDED:
            return Response(
                {"error": "Abonnement suspendu : le changement de formule est impossible."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if subscription.status == Subscription.Status.CANCELLED:
            return Response(
                {"error": "Abonnement annulé : souscrivez à nouveau pour changer de formule."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if subscription.status not in (Subscription.Status.ACTIVE, Subscription.Status.PENDING, Subscription.Status.EXPIRED):
            return Response(
                {"error": "Aucun abonnement actif à modifier."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if subscription.plan.code == plan.code:
            return Response(
                {"error": "Vous êtes déjà sur la formule demandée."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pending = _pending_payment_for(subscription)
        if pending:
            return Response(
                {"error": "Un paiement est déjà en attente pour cet abonnement.", "payment": pending.id},
                status=status.HTTP_409_CONFLICT,
            )

        from apps.payments.models import Payment
        from apps.payments.serializers import PaymentSerializer

        payment = Payment.objects.create(
            subscription=subscription, amount=plan.price, currency="XOF",
            method=request.data.get("payment_method", "wave"),
            metadata={"action": "change_plan", "plan_code": plan.code},
        )
        return Response({"payment": PaymentSerializer(payment).data}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="history")
    def history(self, request):
        """Historique du cycle de vie de l'abonnement du commercant (immuable)."""
        _require_merchant(request.user)
        qs = SubscriptionHistory.objects.filter(subscription__subscriber_id=request.user.id)
        return Response(SubscriptionHistorySerializer(qs[:50], many=True).data)

    @action(detail=False, methods=["get"], url_path="payments")
    def payments(self, request):
        """Paiements d'abonnement du commercant (souscription, renouvellement, changement)."""
        _require_merchant(request.user)
        from apps.payments.models import Payment
        from apps.payments.serializers import PaymentSerializer

        qs = Payment.objects.filter(subscription__subscriber_id=request.user.id)
        return Response(PaymentSerializer(qs[:50], many=True).data)

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


class SubscriptionHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Historique immutable : le commercant voit le sien, l'admin tout."""
    serializer_class = SubscriptionHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin():
            return SubscriptionHistory.objects.all()
        return SubscriptionHistory.objects.filter(seller=user)


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    """Factures liées aux abonnements du commerçant connecté ; l'admin voit tout."""
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin():
            return Invoice.objects.all()
        return Invoice.objects.filter(subscription__subscriber_id=user.id)


class SponsoredProductViewSet(viewsets.ModelViewSet):
    """Un commerçant gère la mise en avant de ses propres produits ; l'admin voit et gère tout."""
    serializer_class = SponsoredProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin():
            return SponsoredProduct.objects.all()
        return SponsoredProduct.objects.filter(store__owner=user)

    def perform_create(self, serializer):
        user = self.request.user
        store = serializer.validated_data.get("store")
        if not user.is_admin() and store.owner_id != user.id:
            raise PermissionDenied("Vous ne pouvez sponsoriser que les produits de votre propre boutique.")
        serializer.save()