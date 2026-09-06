from decimal import Decimal
import json
import time

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.response import Response
from .models import Address, Delivery, DeliveryTracking, Driver, Order, OrderItem
from .pricing import compute_delivery_fee
from .realtime import subscribe_delivery_events
from .serializers import (
    AddressSerializer, CheckoutSerializer, DeliveryQuoteSerializer, DeliverySerializer,
    DeliveryTrackingSerializer, DriverSerializer, OrderSerializer,
)
from apps.catalog.models import ProductVariant, Store
from apps.payments.models import Payment, Refund
from apps.shopping.models import CartItem
from apps.users.models import Role
from apps.kyc.utils import driver_kyc_verified


class AddressViewSet(viewsets.ModelViewSet):
    """Carnet d'adresses de l'utilisateur connecté."""
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class OrderViewSet(viewsets.ModelViewSet):
    """
    Un acheteur voit ses propres commandes, un vendeur celles de ses boutiques,
    un livreur celles dont la livraison lui est affectée, l'admin voit tout.
    """

    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.has_role(Role.RoleName.ADMIN):
            return Order.objects.all()
        return Order.objects.filter(
            models.Q(customer=user) | models.Q(store__owner=user) | models.Q(delivery__driver__user=user)
        ).distinct()

    @action(detail=False, methods=["post"])
    def quote(self, request):
        """Prévisualise le frais de livraison (même formule que le checkout) avant paiement."""
        serializer = DeliveryQuoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        store = get_object_or_404(Store, pk=data["store"])
        address = get_object_or_404(Address, pk=data["address"], user=request.user)
        fee = compute_delivery_fee(store, address, data["delivery_type"])
        return Response({"delivery_fee": str(fee)})

    @action(detail=False, methods=["post"])
    def checkout(self, request):
        """
        Construit, en une transaction, la commande, ses lignes, sa livraison
        et son paiement en attente à partir du panier validé côté frontend
        (écrans checkout-address / -delivery / -payment), puis retire du
        panier les articles achetés.
        """
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        store = get_object_or_404(Store, pk=data["store"])
        address = get_object_or_404(Address, pk=data["address"], user=request.user)
        delivery_fee = compute_delivery_fee(store, address, data["delivery_type"])

        # Gating commission (spec §17-§18) : au-delà de la période de grâce,
        # un vendeur sans essai ni abonnement payé actif ne reçoit plus de
        # nouvelles commandes — ses données historiques ne sont jamais touchées.
        from apps.commissions.services import can_receive_orders
        if not can_receive_orders(store.owner):
            raise ValidationError(
                "Ce vendeur ne peut plus recevoir de nouvelles commandes "
                "(abonnement commerçant expiré). Choisissez une autre boutique."
            )

        with transaction.atomic():
            order = Order.objects.create(
                customer=request.user,
                store=store,
                address=address,
                delivery_fee=delivery_fee,
            )

            total = Decimal("0")
            for item in data["items"]:
                variant = get_object_or_404(
                    ProductVariant.objects.select_related("product"),
                    pk=item["product_variant"],
                    product__store=store,
                )
                inventory = getattr(variant, "inventory", None)
                if inventory is not None and not inventory.reserve(item["quantity"]):
                    raise ValidationError(
                        f"Stock insuffisant pour « {variant.product.name} » ({variant.sku}). "
                        f"Disponible : {inventory.available()}."
                    )
                order_item = OrderItem.objects.create(
                    order=order,
                    product_variant=variant,
                    quantity=item["quantity"],
                    unit_price=variant.price,
                )
                total += order_item.subtotal()

            order.total_amount = total + order.delivery_fee
            order.save(update_fields=["total_amount"])

            Delivery.objects.create(order=order)
            Payment.objects.create(
                order=order,
                amount=order.total_amount,
                method=data["payment_method"],
            )

            variant_ids = [item["product_variant"] for item in data["items"]]
            CartItem.objects.filter(
                cart__user=request.user, product_variant_id__in=variant_ids
            ).delete()

        from apps.analytics.models import SalesStatistic
        SalesStatistic.compute_for_store(store, order.created_at.date())

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Annule une commande encore annulable (client, boutique concernée ou admin)."""
        order = self.get_object()
        user = request.user
        is_allowed = (
            order.customer_id == user.id
            or order.store.owner_id == user.id
            or user.has_role(Role.RoleName.ADMIN)
        )
        if not is_allowed:
            raise PermissionDenied("Vous ne pouvez annuler que vos propres commandes.")
        if not order.can_be_cancelled():
            raise ValidationError(f"Une commande au statut « {order.status} » ne peut plus être annulée.")

        order.change_status(Order.Status.CANCELLED)
        delivery = getattr(order, "delivery", None)
        if delivery and delivery.status in [Delivery.Status.PENDING, Delivery.Status.ASSIGNED]:
            delivery.cancel()
        order.notify_merchant_cancelled()

        payment = getattr(order, "payment", None)
        if payment and payment.status == Payment.Status.SUCCESS:
            # La commande était déjà payée : sans ça, l'argent restait
            # marqué "encaissé" sans que rien n'indique qu'il faut le
            # rendre. Le remboursement est créé "pending" ici ; un admin le
            # traite ensuite (voir RefundViewSet.process) — un remboursement
            # Wave/Orange Money/carte n'est pas instantané.
            Refund.objects.create(
                payment=payment, amount=payment.amount, reason="Commande annulée par le client",
            )

        return Response(OrderSerializer(order).data)


class DriverViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lecture des profils livreur : un admin voit tout, un commerçant voit les
    livreurs disponibles (pour affecter une livraison), un livreur ne voit
    que lui-même sauf via l'action `me`.
    """
    serializer_class = DriverSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.has_role(Role.RoleName.ADMIN):
            return Driver.objects.all()
        if user.has_role(Role.RoleName.MERCHANT):
            return Driver.objects.filter(availability_status=Driver.AvailabilityStatus.AVAILABLE)
        return Driver.objects.filter(user=user)

    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        """Profil livreur de l'utilisateur connecté, créé à la volée s'il n'existe pas encore."""
        if not request.user.has_role(Role.RoleName.DRIVER):
            raise PermissionDenied("Seul un compte livreur possède un profil livreur.")
        driver, _ = Driver.objects.get_or_create(user=request.user)
        if request.method == "PATCH":
            if "vehicle_type" in request.data:
                driver.vehicle_type = request.data["vehicle_type"]
            if "availability_status" in request.data:
                # Gating KYC (spec §21) : un livreur ne peut se rendre
                # disponible (donc accepter des courses) que si son identité
                # (DriverKYC) a été vérifiée.
                if (
                    request.data["availability_status"] == Driver.AvailabilityStatus.AVAILABLE
                    and not driver_kyc_verified(request.user)
                ):
                    raise PermissionDenied(
                        "Votre identité (KYC) doit être vérifiée par un administrateur "
                        "avant de pouvoir accepter des livraisons."
                    )
                driver.availability_status = request.data["availability_status"]
            if "zone" in request.data:
                driver.zone_id = request.data["zone"]
            driver.save()
        return Response(DriverSerializer(driver).data)


class DeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Livraisons : un livreur voit celles qui lui sont affectées, un commerçant
    celles de ses commandes, l'admin voit tout. La livraison elle-même est
    créée automatiquement par `OrderViewSet.checkout`, pas ici.
    """
    serializer_class = DeliverySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.has_role(Role.RoleName.ADMIN):
            return Delivery.objects.all()
        if user.has_role(Role.RoleName.DRIVER):
            return Delivery.objects.filter(driver__user=user)
        return Delivery.objects.filter(order__store__owner=user)

    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request, pk=None):
        """Le commerçant affecte un livreur affilié disponible à la livraison de sa commande."""
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        if not user.has_role(Role.RoleName.ADMIN) and delivery.order.store.owner_id != user.id:
            raise PermissionDenied("Vous ne pouvez affecter un livreur qu'à vos propres commandes.")
        driver = get_object_or_404(Driver, pk=request.data.get("driver"))
        delivery.assign_driver(driver)
        delivery.broadcast_status(
            f"Votre commande est prise en charge par {driver.user.get_full_name() or driver.user.email}."
        )
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=["post"], url_path="status")
    def update_status(self, request, pk=None):
        """Le livreur affecté fait progresser le statut de sa course."""
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        is_assigned_driver = delivery.driver and delivery.driver.user_id == user.id
        if not user.has_role(Role.RoleName.ADMIN) and not is_assigned_driver:
            raise PermissionDenied("Seul le livreur affecté peut mettre à jour cette livraison.")

        new_status = request.data.get("status")
        allowed_transitions = {
            Delivery.Status.ASSIGNED: [Delivery.Status.PICKED_UP],
            Delivery.Status.PICKED_UP: [Delivery.Status.DELIVERED],
        }
        if new_status not in allowed_transitions.get(delivery.status, []):
            raise ValidationError(
                f"Transition invalide de « {delivery.status} » vers « {new_status} »."
            )

        delivery.status = new_status
        if new_status == Delivery.Status.PICKED_UP:
            delivery.picked_up_at = timezone.now()
        elif new_status == Delivery.Status.DELIVERED:
            delivery.delivered_at = timezone.now()
        delivery.save()

        if new_status == Delivery.Status.DELIVERED:
            delivery.order.change_status(Order.Status.DELIVERED, changed_by=user)

        status_messages = {
            Delivery.Status.ASSIGNED: "Un livreur vous est affecté.",
            Delivery.Status.PICKED_UP: "Le livreur a récupéré votre colis : en route !",
            Delivery.Status.DELIVERED: "Votre commande est livrée. Bonne réception !",
        }
        delivery.broadcast_status(status_messages.get(delivery.status, ""))

        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=["post"], url_path="track")
    def track(self, request, pk=None):
        """Le livreur affecté partage sa position GPS courante."""
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        is_assigned_driver = delivery.driver and delivery.driver.user_id == user.id
        if not user.has_role(Role.RoleName.ADMIN) and not is_assigned_driver:
            raise PermissionDenied("Seul le livreur affecté peut partager sa position.")

        serializer = DeliveryTrackingSerializer(data={**request.data, "delivery": delivery.id})
        serializer.is_valid(raise_exception=True)
        tracking = serializer.save()
        tracking.broadcast()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DeliveryEventStreamView(viewsets.ViewSet):
    """
    Flux Server-Sent Events d'une livraison (SSE, HTTP long-message).

    GET /api/orders/deliveries/{id}/events/?access_token=<jwt>

    Le client, le commerçant concerné, le livreur affecté ou l'admin reçoivent
    en direct les positions GPS et les changements de statut poussés sur le
    canal Redis (`apps.orders.realtime`). Le `<EventSource>` navigateur ne peut
    pas poser d'en-tête `Authorization`, d'où le token en query string — le
    Bearer header reste accepté pour les autres clients.

    Dégradations assumées :
    - sans Redis, le flux renvoie l'instantané puis des keep-alives (le
      frontend garde son polling de secours de 10 s) ;
    - un événement publié avant la connexion n'est pas ré-expédié (le flux est
      un journal « from now on », pas un historique).
    """
    permission_classes = [permissions.AllowAny]  # auth gérée manuellement ci-dessous

    def _authenticate(self, request):
        if request.user.is_authenticated:
            return request.user
        access = request.query_params.get("access_token") or request.query_params.get("token")
        if access:
            User = get_user_model()
            from rest_framework_simplejwt.exceptions import TokenError
            from rest_framework_simplejwt.tokens import AccessToken
            try:
                payload = AccessToken(access)
                request.user = User.objects.get(pk=payload["user_id"])
                return request.user
            except (TokenError, User.DoesNotExist, KeyError):
                raise AuthenticationFailed("Le jeton du flux est invalide ou expiré.")
        raise AuthenticationFailed("Authentification requise pour suivre cette livraison.")

    def _delivery_for(self, user, delivery_id):
        delivery = get_object_or_404(Delivery, pk=delivery_id)
        is_allowed = (
            delivery.order.customer_id == user.id
            or delivery.order.store.owner_id == user.id
            or (delivery.driver_id and delivery.driver.user_id == user.id)
            or user.has_role(Role.RoleName.ADMIN)
        )
        if not is_allowed:
            raise PermissionDenied("Vous n'êtes pas autorisé à suivre cette livraison.")
        return delivery

    def _sse(self, event, payload):
        data = json.dumps({"event": event, **payload}, default=str)
        return f"data: {data}\n\n"

    def _event_stream(self, delivery, pubsub):
        # 1. Instantané de connexion : l'écran se positionne tout de suite
        #    sans attendre l'événement suivant.
        yield self._sse("snapshot", delivery.event_payload())
        if pubsub is None:
            while True:  # Redis coupé : keep-alives, le client bascule en polling.
                yield ": keep-alive\n\n"
                time.sleep(15)
        try:
            while True:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if message is None:
                    yield ": keep-alive\n\n"
                    continue
                raw = message.get("data")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    parsed = json.loads(raw)
                    event = parsed.pop("event", "event")
                    yield self._sse(event, parsed)
                except (TypeError, ValueError):
                    yield f"data: {raw}\n\n"
        finally:
            pubsub.close()

    def get(self, request, pk=None):
        user = self._authenticate(request)
        delivery = self._delivery_for(user, pk)
        _, pubsub = subscribe_delivery_events(pk)
        response = StreamingHttpResponse(
            self._event_stream(delivery, pubsub),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
