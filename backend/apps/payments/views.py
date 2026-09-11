import json
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
from .gateways import (
    PaymentGatewayError, get_gateway, verify_orange_notification, verify_wave_signature,
)
from apps.monetization.models import Notification
from apps.orders.models import Order
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


def _fulfill_payment(payment, changed_by=None):
    """Traite un paiement confirmé réussi, quel que soit le canal (sandbox,
    webhook Wave, webhook Orange Money). Idempotent : `mark_succeeded` ne
    ré-exécute jamais deux fois commissions/abonnement, et le changement de
    statut de commande est lui aussi sauf."""
    payment.mark_succeeded()
    if payment.order_id is not None:
        payment.order.change_status(Order.Status.PAID, changed_by=changed_by)
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
        except PaymentGatewayError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except NotImplementedError as exc:
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
            _fulfill_payment(payment, changed_by=request.user)
        else:
            payment.mark_failed()
        return Response(PaymentSerializer(payment).data)


class PaymentWebhookView(APIView):
    """
    Endpoint public de notification fournisseur, idempotent.

    POST /api/payments/webhook/{provider}/

    * ``provider="wave"`` : Wave Business envoie l'événement
      ``checkout.session.completed`` (la session dans ``data``), signé HMAC
      (entête ``Wave-Signature``). La signature est vérifiée avec
      ``WAVE_WEBHOOK_SECRET`` avant toute lecture du corps.
    * ``provider="orange_money"`` : Orange envoie
      ``{"status": "SUCCESS", "notif_token": ..., "txnid": ...}``. La seule
      authentification possible est la correspondance du ``notif_token`` avec
      celui reçu à la création du paiement (stocké dans Payment.metadata).

    En mode sandbox (``PAYMENT_SANDBOX`` actif), les deux acceptent aussi le
    format générique ``{"reference", "status"}`` utilisé par SandboxGateway
    pour tester le cycle de vie complet.

    Sécurité : aucun paiement n'est confirmé sans que le backend retrouve le
    Payment à confirmer, et jamais sans signature/token valide hors sandbox.
    """

    permission_classes = [permissions.AllowAny]

    def _reject(self, request, reason, code=status.HTTP_403_FORBIDDEN):
        provider = self.kwargs.get("provider")
        log_security_event(
            None, "payment.webhook.rejected", request,
            {"provider": provider, "reason": reason},
        )
        return Response({"error": "Notification fournisseur non authentifiée."}, status=code)

    def _find_payment_by_ref(self, reference):
        if not reference:
            return None
        if _is_uuid(reference):
            return Payment.objects.filter(id=reference).first()
        return Payment.objects.filter(provider_ref=reference).first()

    def _handle_wave(self, data):
        """Événement Wave, signature déjà vérifiée. Retourne (payment, outcome)."""
        event = data.get("data", data) if isinstance(data, dict) else {}
        if isinstance(event, dict) and event.get("type"):
            # Enveloppe événement : {id, type, data}
            event = event.get("data") or {}
        if not isinstance(event, dict):
            return None, None
        event_type = data.get("type") if isinstance(data, dict) else None
        if event_type and event_type != "checkout.session.completed":
            return None, None
        payment = self._find_payment_by_ref(event.get("client_reference"))
        if payment is None:
            payment = self._find_payment_by_ref(event.get("id"))
        if payment is None:
            return None, None
        ps = str(event.get("payment_status") or "").lower()
        if ps in ("succeeded", "fulfilled"):
            return payment, "success"
        if ps in ("cancelled", "expired") or str(event.get("checkout_status") or "").lower() == "expired":
            return payment, "failed"
        return payment, None

    def _handle_orange(self, payload):
        """Notification Orange Money, token vérifié. Retourne (payment, outcome)."""
        notif_token = payload.get("notif_token") if isinstance(payload, dict) else None
        status_value = str((payload or {}).get("status") or "").upper()

        # La notif_token est propre à chaque demande de paiement : c'est
        # notre référentiel de rapprochement (le corps d'une notification
        # Orange ne transporte que status/notif_token/txnid).
        payment = None
        if notif_token:
            payment = Payment.objects.filter(
                metadata__orange_money__notif_token=notif_token
            ).first()
        if payment is None and (payload or {}).get("order_id"):
            payment = Payment.objects.filter(
                metadata__orange_money__order_id=payload["order_id"]
            ).first()
        if payment is None:
            payment = self._find_payment_by_ref((payload or {}).get("txnid"))
        if payment is None:
            return None, None
        if not verify_orange_notification(payment, notif_token):
            return payment, "rejected"
        if status_value == "SUCCESS":
            return payment, "success"
        if status_value in ("FAILED", "EXPIRED"):
            return payment, "failed"
        return payment, None

    def post(self, request, provider):
        raw_body = getattr(request, "body", b"")

        # --- Authentification fournisseur (hors sandbox) ---
        if not settings.PAYMENT_SANDBOX:
            if provider == "wave":
                secret = settings.PAYMENT_PROVIDERS.get("wave")
                signature_header = request.headers.get("Wave-Signature") or request.headers.get("X-Wave-Signature")
                if not secret or not signature_header or not verify_wave_signature(secret, signature_header, raw_body):
                    return self._reject(request, "signature_wave_invalide")
            elif provider not in ("wave", "orange_money"):
                return self._reject(request, "provider_not_configured", code=status.HTTP_503_SERVICE_UNAVAILABLE)
            # orange_money : l'authentification se fait paiement par paiement
            # via le notif_token (voir _handle_orange) — aucun secret global.

        try:
            payload = json.loads(raw_body or b"{}")
        except ValueError:
            return Response({"error": "Corps JSON invalide."}, status=status.HTTP_400_BAD_REQUEST)

        # --- Branchement par fournisseur (hors sandbox) ---
        if not settings.PAYMENT_SANDBOX:
            if provider == "wave":
                payment, outcome = self._handle_wave(payload)
            elif provider == "orange_money":
                payment, outcome = self._handle_orange(payload)
            else:
                payment, outcome = None, None
            if payment is None:
                log_security_event(
                    None, "payment.webhook.unknown_payment", request,
                    {"provider": provider, "reference": json.dumps(payload)[:160]},
                )
                return Response(
                    {"error": "Paiement introuvable pour cette notification."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if outcome == "rejected":
                return self._reject(request, "notif_token_invalide")
            if outcome is None:
                return Response({"received": True, "status": "ignored"})
            already = payment.status
            if outcome == "success":
                _fulfill_payment(payment)
            else:
                payment.mark_failed()
            if already == Payment.Status.SUCCESS:
                log_security_event(
                    None, "payment.webhook.deduplicated", request,
                    {"provider": provider, "payment_id": str(payment.id)},
                )
            return Response({
                "received": True,
                "payment_id": payment.id,
                "status": payment.status,
                "duplicate": already == Payment.Status.SUCCESS,
            })

        # --- Format générique sandbox (simulation du cycle de vie) ---
        reference = str(payload.get("reference", "")).strip()
        outcome = str(payload.get("status", "")).lower()
        if not reference or outcome not in ("success", "failed"):
            return Response(
                {"error": "reference et status ('success'|'failed') sont requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = self._find_payment_by_ref(reference)
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
            _fulfill_payment(payment)
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

