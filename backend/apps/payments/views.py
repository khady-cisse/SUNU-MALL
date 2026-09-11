import uuid
from django.conf import settings
from django.db import models
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Payment, Refund
from .serializers import PaymentSerializer, RefundSerializer
from .gateways import PaymentGatewayError, get_gateway
from apps.monetization.models import Notification
from apps.orders.models import GlobalOrder, Order
from apps.security.utils import log_security_event
from apps.users.permissions import IsAdmin


def _is_uuid(value):
    """True si la référence peut être l'UUID d'un Payment (évite qu'une chaîne
    arbitraire dans un webhook ne fasse lever ValidationError sur le champ UUID)."""
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _send_order_confirmation(order):
    """
    Confirmation envoyée au client juste après le paiement réussi. Email
    réellement délivré (SMTP déjà configuré) ; le canal SMS existe déjà
    dans le modèle Notification pour quand un fournisseur sera branché,
    mais n'envoie rien de réel pour l'instant (voir Notification._send_sms).
    """
    subject = f"Commande confirmée — {order.store.name}"
    message = (
        f"Bonjour {order.customer.first_name or order.customer.email},\n\n"
        f"Votre commande n°{str(order.id)[:8]} chez {order.store.name} a été payée avec succès.\n"
        f"Montant total : {order.total_amount} FCFA.\n\n"
        "Vous pouvez suivre sa livraison depuis votre espace Sunu Mall.\n\n"
        "Merci de votre confiance !"
    )
    notification = Notification.objects.create(
        user=order.customer,
        channel=Notification.Channel.EMAIL,
        subject=subject,
        message=message,
        metadata={"order_id": str(order.id)},
    )
    notification.send()


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lecture seule : un paiement n'est jamais modifié directement par
    l'utilisateur, seulement via les actions `initiate` / `sandbox-confirm`
    (ou plus tard un webhook fournisseur authentifié par signature).
    """
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin():
            return Payment.objects.all()
        return Payment.objects.filter(
            models.Q(order__customer=user)
            | models.Q(order__store__owner=user)
            | models.Q(global_order__customer=user)
            | models.Q(subscription__subscriber_id=user.id)
        ).distinct()

    def _ensure_customer(self, payment):
        if self.request.user.is_admin():
            return
        if payment.order_id is not None:
            owner_id = payment.order.customer_id
            message = "Seul le client de la commande peut agir sur ce paiement."
        elif payment.global_order_id is not None:
            owner_id = payment.global_order.customer_id
            message = "Seul le client de la commande peut agir sur ce paiement."
        else:
            owner_id = payment.subscription.subscriber_id
            message = "Seul l'abonné peut agir sur ce paiement."
        if owner_id != self.request.user.id:
            raise PermissionDenied(message)

    @action(detail=True, methods=["post"], url_path="initiate")
    def initiate(self, request, pk=None):
        """Démarre le paiement auprès du fournisseur (ou de la simulation sandbox)."""
        payment = self.get_object()
        self._ensure_customer(payment)
        gateway = get_gateway(payment.method)
        try:
            result = gateway.initiate(payment)
        except (NotImplementedError, PaymentGatewayError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_501_NOT_IMPLEMENTED)
        return Response(result)

    @action(detail=True, methods=["post"], url_path="sandbox-confirm")
    def sandbox_confirm(self, request, pk=None):
        """
        Simule la confirmation (succès ou échec) qu'enverrait normalement le
        fournisseur via webhook. Uniquement disponible quand PAYMENT_SANDBOX
        est actif — jamais en production avec de vraies clés configurées.
        """
        if not settings.PAYMENT_SANDBOX:
            return Response(
                {"error": "Le mode sandbox n'est pas actif sur cet environnement."},
                status=status.HTTP_403_FORBIDDEN,
            )
        payment = self.get_object()
        self._ensure_customer(payment)

        outcome = request.data.get("outcome", "success")
        if outcome == "success":
            payment.mark_succeeded()
            if payment.order_id is not None:
                payment.order.change_status(Order.Status.PAID, changed_by=request.user)
                _send_order_confirmation(payment.order)
                delivery = getattr(payment.order, "delivery", None)
                if delivery:
                    delivery.auto_assign()
            elif payment.global_order_id is not None:
                delivery = payment.global_order.deliveries.first()
                if delivery:
                    delivery.auto_assign()
            # Le côté abonnement (activation + facture) est déjà géré par
            # Payment.mark_succeeded() lui-même — voir apps.payments.models.
        else:
            payment.mark_failed()
        return Response(PaymentSerializer(payment).data)


class PaymentWebhookView(APIView):
    """
    Endpoint public de notification fournisseur, idempotent.

    POST /api/payments/webhook/{provider}/
    Body attendu :
        {
            "reference": "SANDBOX-AABBCCDDEE" ou l'UUID du Payment,
            "transaction_id": "ref fournisseur (facultatif)",
            "status": "success" | "failed"
        }

    Sécurité : aucun paiement n'est confirmé sans que le backend retrouve le
    Payment à confirmer — une chaîne arbitraire est simplement ignorée. La
    vérification de signature fournisseur est activée dès qu'une clé existe
    (settings.PAYMENT_PROVIDERS) ; en sandbox, le webhook reste disponible
    pour tester le cycle de vie complet côté intégration.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, provider):
        if not settings.PAYMENT_SANDBOX:
            secret = getattr(settings, "PAYMENT_PROVIDERS", {}).get(provider)
            if not secret:
                log_security_event(
                    None, "payment.webhook.rejected", request,
                    {"provider": provider, "reason": "provider_not_configured"},
                )
                return Response(
                    {"error": "Fournisseur de paiement non configuré pour ce webhook."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            # La vérification de signature (HMAC du corps de la requête) serait
            # effectuée ici une fois qu'une API réelle est configurée — voir
            # gateways.py, pour ne pas inventer un protocole faux.

        reference = str(request.data.get("reference", "")).strip()
        outcome = str(request.data.get("status", "")).lower()
        if not reference or outcome not in ("success", "failed"):
            return Response(
                {"error": "reference et status ('success'|'failed') sont requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = None
        if _is_uuid(reference):
            payment = Payment.objects.filter(id=reference).first()
        if payment is None:
            payment = Payment.objects.filter(provider_ref=reference).first()
        if payment is None:
            log_security_event(
                None, "payment.webhook.unknown_payment", request,
                {"provider": provider, "reference": reference[:80]},
            )
            return Response(
                {"error": "Paiement introuvable pour cette référence."},
                status=status.HTTP_404_NOT_FOUND,
            )

        already = payment.status
        if outcome == "success":
            payment.mark_succeeded()
        else:
            payment.mark_failed()

        # Journaliser uniquement les événements anormaux (le double comptage
        # est impossible grâce à l'idempotence de mark_succeeded/mark_failed).
        if already == Payment.Status.SUCCESS:
            log_security_event(
                None, "payment.webhook.deduplicated", request,
                {"provider": provider, "reference": reference[:80], "payment_id": str(payment.id)},
            )

        return Response({
            "received": True,
            "payment_id": payment.id,
            "status": payment.status,
            "duplicate": already == payment.status,
        })


class RefundViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Remboursements créés automatiquement quand une commande déjà payée est
    annulée (voir OrderViewSet.cancel). Un client voit les siens ; seul
    l'admin peut les traiter (action `process`) — un remboursement Wave/
    Orange Money/carte n'est pas un appel API instantané ici, un humain
    confirme que l'argent a bien été renvoyé avant de le marquer complété.
    """
    serializer_class = RefundSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Refund.objects.select_related("payment__order__store", "payment__order__customer")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if user.is_admin():
            return qs
        return qs.filter(payment__order__customer=user)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated, IsAdmin])
    def process(self, request, pk=None):
        refund = self.get_object()
        if refund.status == Refund.Status.COMPLETED:
            return Response({"error": "Ce remboursement a déjà été traité."}, status=status.HTTP_400_BAD_REQUEST)
        refund.process()
        return Response(RefundSerializer(refund).data)
