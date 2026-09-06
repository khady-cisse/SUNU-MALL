from decimal import Decimal
import json
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import get_random_string
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
from apps.users.models import Role, UserRole
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

    Avec le paramètre `?store=<uuid>`, seuls les livreurs disponibles situés
    à moins de `DRIVER_ASSIGNMENT_RADIUS_KM` km de la boutique sont renvoyés
    (chacun avec sa `distance_km`), pour satisfaire la règle métier :
    un livreur ne peut récupérer une commande que s'il est près de la boutique.
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

    def list(self, request, *args, **kwargs):
        store_id = request.query_params.get("store")
        store = None
        if store_id and (
            request.user.has_role(Role.RoleName.ADMIN) or request.user.has_role(Role.RoleName.MERCHANT)
        ):
            store = (
                Store.objects.filter(pk=store_id, latitude__isnull=False, longitude__isnull=False).first()
            )
        queryset = self.get_queryset()
        if store is not None:
            # Filtre « à proximité de la boutique » : réponse non paginée simple.
            driver_list = list(queryset)
            radius = settings.DRIVER_ASSIGNMENT_RADIUS_KM
            driver_list = [
                d
                for d in driver_list
                if (distance := d.distance_to_store_km(store)) is not None and distance <= radius
            ]
            serializer = self.get_serializer(driver_list, many=True, context={"store": store})
            return Response(serializer.data)
        # Chemin standard paginé.
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="register")
    def register_driver(self, request):
        """Crée un compte livreur (admin uniquement) : nom, prénom, email,
        téléphone, type de véhicule. Le mot de passe provisoire est renvoyé
        une seule fois ; le livreur devra le changer à sa première connexion."""
        User = get_user_model()
        if not request.user.has_role(Role.RoleName.ADMIN):
            raise PermissionDenied("Seul un administrateur peut créer un compte livreur.")

        email = (request.data.get("email") or "").strip().lower()
        first_name = (request.data.get("first_name") or "").strip()
        last_name = (request.data.get("last_name") or "").strip()
        phone = (request.data.get("phone") or "").strip()
        vehicle_type = (request.data.get("vehicle_type") or "").strip()

        missing = [f for f, v in {
            "email": email, "first_name": first_name, "last_name": last_name, "vehicle_type": vehicle_type,
        }.items() if not v]
        if missing:
            raise ValidationError(f"Champs manquants : {', '.join(missing)}.")

        if User.objects.filter(email=email).exists():
            raise ValidationError("Un compte existe déjà avec cet email.")

        temporary_password = get_random_string(10)
        user = User.objects.create_user(
            username=email,
            email=email,
            password=temporary_password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            is_verified=True,
            must_change_password=True,
        )
        role = Role.objects.get(name=Role.RoleName.DRIVER)
        UserRole.objects.create(user=user, role=role)
        driver = Driver.objects.create(
            user=user,
            vehicle_type=vehicle_type,
            availability_status=Driver.AvailabilityStatus.OFFLINE,
        )
        data = DriverSerializer(driver).data
        data["temporary_password"] = temporary_password
        return Response(data, status=status.HTTP_201_CREATED)

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

    @action(detail=False, methods=["post"], url_path="me/position")
    def update_my_position(self, request):
        """Le livreur enregistre sa position GPS libre (hors course), utilisée
        pour vérifier sa proximité avec la boutique avant une affectation."""
        if not request.user.has_role(Role.RoleName.DRIVER):
            raise PermissionDenied("Seul un compte livreur peut partager sa position.")
        latitude = request.data.get("latitude")
        longitude = request.data.get("longitude")
        if latitude is None or longitude is None:
            raise ValidationError("latitude et longitude sont requises.")
        try:
            driver, _ = Driver.objects.get_or_create(user=request.user)
            driver.last_latitude = Decimal(str(latitude))
            driver.last_longitude = Decimal(str(longitude))
            driver.position_updated_at = timezone.now()
            driver.save()
        except (ValueError, TypeError):
            raise ValidationError("Coordonnées invalides.")
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
        """Le commerçant (ou l'admin) affecte un livreur à la livraison de sa commande.

        Règle métier : le livreur doit se trouver à moins de
        `DRIVER_ASSIGNMENT_RADIUS_KM` km de la boutique — il doit être assez
        proche pour venir récupérer le colis avant de livrer le client.
        """
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        if not user.has_role(Role.RoleName.ADMIN) and delivery.order.store.owner_id != user.id:
            raise PermissionDenied("Vous ne pouvez affecter un livreur qu'à vos propres commandes.")
        driver = get_object_or_404(Driver, pk=request.data.get("driver"))

        store = delivery.order.store
        if store.latitude is None or store.longitude is None:
            raise ValidationError(
                "La boutique n'a pas de coordonnées GPS : impossible de vérifier où récupérer le colis."
            )
        distance = driver.distance_to_store_km(store)
        radius = settings.DRIVER_ASSIGNMENT_RADIUS_KM
        if distance is None:
            raise ValidationError(
                "Ce livreur n'a pas signalé sa position. Il doit partager sa position GPS "
                "(être près de la boutique) avant de pouvoir se voir confier une course."
            )
        if distance > radius:
            raise ValidationError(
                f"Ce livreur est à {distance:.1f} km de la boutique ({radius:.0f} km max). "
                f"Affectez un livreur situé à proximité."
            )

        delivery.assign_driver(driver)
        delivery.broadcast_status(
            f"Votre commande est prise en charge par {driver.user.get_full_name() or driver.user.email}."
        )
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=["post"], url_path="status")
    def update_status(self, request, pk=None):
        """Le livreur affecté fait progresser le statut de sa course.

        Jusqu'à « colis récupéré » (picked_up) : à ce moment, un code de
        confirmation OTP est généré et remis au livreur (dans la réponse,
        une seule fois) — le livreur le communique physiquement au client.
        La transition vers « livré » n'est PAS possible par le livreur : elle
        est validée par le client via `confirm` (code OTP), ou par un admin
        (dépannage) via cette même action.
        """
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        is_assigned_driver = delivery.driver and delivery.driver.user_id == user.id
        is_admin = user.has_role(Role.RoleName.ADMIN)
        if not is_admin and not is_assigned_driver:
            raise PermissionDenied("Seul le livreur affecté peut mettre à jour cette livraison.")

        new_status = request.data.get("status")
        allowed_transitions = {
            Delivery.Status.ASSIGNED: [Delivery.Status.PICKED_UP, *([Delivery.Status.DELIVERED] if is_admin else [])],
            Delivery.Status.PICKED_UP: [Delivery.Status.DELIVERED] if is_admin else [],
        }
        if new_status not in allowed_transitions.get(delivery.status, []):
            raise ValidationError(
                f"Transition invalide de « {delivery.status} » vers « {new_status} »."
            )

        delivery.status = new_status
        confirmation_code = None
        if new_status == Delivery.Status.PICKED_UP:
            delivery.picked_up_at = timezone.now()
            confirmation_code = delivery.generate_confirmation_otp()
            self._notify_customer_pickup(delivery)
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

        data = DeliverySerializer(delivery).data
        if confirmation_code is not None:
            # Le code en clair n'est renvoyé qu'ici (à la génération) : il
            # n'est jamais rejoué par les lectures classiques de la livraison.
            data["confirmation_code"] = confirmation_code
        return Response(data)

    @staticmethod
    def _notify_customer_pickup(delivery):
        """Prévient le client que sa commande est en route (sans jamais
        transmettre le code OTP par email : il est remis en main propre
        par le livreur)."""
        from apps.monetization.models import Notification

        Notification.objects.create(
            user=delivery.order.customer,
            channel=Notification.Channel.EMAIL,
            subject="Votre colis est en route",
            message=(
                f"Bonjour,\n\n"
                f"Votre commande n°{str(delivery.order.id)[:8]} est en cours de livraison.\n\n"
                "À la réception, le livreur vous communiquera un code de confirmation "
                "à saisir sur la page « Confirmer la livraison » pour valider votre commande.\n\n"
                "Merci de votre confiance."
            ),
            metadata={"delivery_id": str(delivery.id), "order_id": str(delivery.order_id)},
        ).send()

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, pk=None):
        """Le client confirme la réception de sa commande avec le code OTP
        remis par le livreur (le destinataire ou un admin)."""
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        is_allowed = delivery.order.customer_id == user.id or user.has_role(Role.RoleName.ADMIN)
        if not is_allowed:
            raise PermissionDenied("Seul le destinataire de la commande peut confirmer la réception.")
        if delivery.status != Delivery.Status.PICKED_UP:
            raise ValidationError("La livraison doit être en cours (colis récupéré) pour être confirmée.")

        code = request.data.get("code", "")
        if not delivery.validate_confirmation_otp(code):
            attempts = delivery.confirmation_attempts
            remaining = max(0, settings.MAX_OTP_ATTEMPTS - attempts)
            detail = "Code de confirmation invalide ou expiré."
            if remaining > 0:
                detail += f" Il vous reste {remaining} essai(s)."
            else:
                detail += " Trop d'essais : demandez au livreur de régénérer un code."
            raise ValidationError(detail)

        delivery.status = Delivery.Status.DELIVERED
        delivery.delivered_at = timezone.now()
        delivery.confirmation_otp_hash = ""
        delivery.confirmation_otp_expires_at = None
        delivery.save()
        delivery.order.change_status(Order.Status.DELIVERED, changed_by=user)
        delivery.broadcast_status("Livraison confirmée par le client. Bonne réception !")
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=["post"], url_path="regenerate-otp")
    def regenerate_otp(self, request, pk=None):
        """Le livreur affecté (ou l'admin) régénère le code de confirmation
        (code perdu, expiré, ou essais épuisés). L'ancien code est invalidé."""
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        is_assigned_driver = delivery.driver and delivery.driver.user_id == user.id
        if not user.has_role(Role.RoleName.ADMIN) and not is_assigned_driver:
            raise PermissionDenied("Seul le livreur affecté peut régénérer un code.")
        if delivery.status != Delivery.Status.PICKED_UP:
            raise ValidationError("Aucun code à régénérer dans l'état actuel de la course.")

        code = delivery.generate_confirmation_otp()
        data = DeliverySerializer(delivery).data
        data["confirmation_code"] = code
        return Response(data)

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
