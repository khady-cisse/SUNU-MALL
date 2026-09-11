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
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from .models import (
    Address, Delivery, DeliveryEvent, DeliveryPartner, DeliveryPickup,
    DeliveryPricingRule, DeliveryTracking, Driver, GlobalOrder, Order,
    OrderItem, PartnerInvoice, PartnerZonePricing,
)
from .pricing import (
    best_delivery_partner, compute_delivery_fee, compute_delivery_fee_multi,
    optimize_route, route_distance_km,
)
from .realtime import subscribe_delivery_events
from .serializers import (
    AddressSerializer, CheckoutSerializer, DeliveryCalculateSerializer,
    DeliveryPickupSerializer, DeliveryPricingRuleSerializer, DeliveryQuoteSerializer,
    DeliverySerializer, DeliveryTrackingSerializer, DriverSerializer,
    GlobalOrderSerializer, OrderSerializer, DeliveryEventSerializer,
    DeliveryPartnerSerializer, DeliveryPartnerDetailSerializer,
    PartnerInvoiceSerializer, PartnerZonePricingSerializer,
)
from apps.catalog.models import Product, ProductVariant, Store
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
        if user.is_admin():
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

    @action(detail=False, methods=["post"], url_path="delivery-calculate")
    def delivery_calculate(self, request):
        """Calcule le tarif de livraison multi-boutiques AVANT paiement (spec §8).

        Entrée : les articles du panier, l'adresse et le type. Les boutiques
        sont déduites des articles (jamais fournies par le client) ; le tarif
        est recalculé par le backend au moment du checkout — le frontend ne
        transmet aucune valeur monétaire.
        """
        serializer = DeliveryCalculateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        address = get_object_or_404(Address, pk=data["address"], user=request.user)

        wants = {str(item["product_variant"]): item["quantity"] for item in data["items"]}
        variants = ProductVariant.objects.filter(id__in=wants.keys()).select_related("product__store")
        if variants.count() != len(wants):
            raise ValidationError("Un article du panier n'existe plus. Actualisez votre panier.")

        stores = {v.product.store for v in variants}
        stores = sorted(stores, key=lambda s: s.name)
        fee = compute_delivery_fee_multi(stores, address, data["delivery_type"])

        distance = None
        coords = [s for s in stores if s.latitude is not None and s.longitude is not None]
        if coords and address.latitude is not None and address.longitude is not None:
            distance = float(route_distance_km(coords, address.latitude, address.longitude))

        return Response({
            "number_of_stores": len(stores),
            "number_of_pickups": len(stores),
            "distance": distance,
            "delivery_fee": str(fee),
            "currency": "XOF",
        })

    @action(detail=False, methods=["post"])
    def checkout(self, request):
        """
        Construit, en une transaction, la commande, ses lignes, sa livraison
        et son paiement en attente à partir du panier validé côté frontend
        (écrans checkout-address / -delivery / -payment), puis retire du
        panier les articles achetés.

        Deux chemins sont possibles :
        - `store` fourni  : commande classique, une boutique (rétrocompatible) ;
        - `store` absent  : commande globale multi-boutiques (GlobalOrder,
          une sous-commande par boutique, une mission avec N points de
          collecte, un paiement unique).

        Le tarif de livraison est TOUJOURS recalculé côté serveur — la valeur
        éventuellement affichée par le frontend n'est jamais reçue.
        """
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get("store"):
            return self._checkout_single(request, data)

        address = get_object_or_404(Address, pk=data["address"], user=request.user)
        return self._checkout_multistore(request, data, address)

    def _checkout_single(self, request, data):
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
                delivery_type=data["delivery_type"],
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
            order.save(update_fields=["total_amount", "delivery_type"])

            delivery = Delivery.objects.create(order=order)
            # Affectation automatique : le meilleur partenaire couvrant la zone
            # (score, taux de réussite) devient responsable de la course (§2, §31).
            partner = best_delivery_partner(address)
            if partner is not None:
                delivery.assign_partner(partner)
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

    def _checkout_multistore(self, request, data, address):
        """
        Passage de commande multi-boutiques : une seule commande globale
        (GlobalOrder), une sous-commande par boutique (Order), une mission de
        livraison décrivant N points de collecte (Delivery + DeliveryPickup),
        un seul paiement global (Payment.global_order).
        """
        delivery_type = data["delivery_type"]
        payment_method = data["payment_method"]

        # 1. Articles → boutiques (jamais confiées au client).
        wants = {str(item["product_variant"]): item["quantity"] for item in data["items"]}
        variants = ProductVariant.objects.filter(id__in=wants.keys()).select_related("product__store", "inventory")
        if variants.count() != len(wants):
            raise ValidationError("Un article du panier n'existe plus. Actualisez votre panier.")

        grouped = {}
        for variant in variants:
            store = variant.product.store
            if store.status != Store.Status.ACTIVE:
                raise ValidationError(
                    f"La boutique « {store.name} » est momentanément indisponible."
                )
            if variant.product.status != Product.Status.ACTIVE:
                raise ValidationError(
                    f"Le produit « {variant.product.name} » n'est plus disponible."
                )
            grouped.setdefault(store, []).append((variant, wants[str(variant.id)]))

        from apps.commissions.services import can_receive_orders
        for store in grouped:
            if not can_receive_orders(store.owner):
                raise ValidationError(
                    f"Le vendeur de « {store.name} » ne peut plus recevoir de nouvelles "
                    "commandes (abonnement commerçant expiré). Retirez ses articles du panier."
                )

        # 2. Tarif recalculé côté serveur (le client ne transmet aucun montant).
        delivery_fee = compute_delivery_fee_multi(list(grouped.keys()), address, delivery_type)

        with transaction.atomic():
            global_order = GlobalOrder.objects.create(
                customer=request.user,
                address=address,
                delivery_type=delivery_type,
            )

            items_total = Decimal("0")
            for store, lines in grouped.items():
                order = Order.objects.create(
                    customer=request.user,
                    store=store,
                    address=address,
                    delivery_type=delivery_type,
                    global_order=global_order,
                )
                subtotal = Decimal("0")
                for variant, quantity in lines:
                    inventory = getattr(variant, "inventory", None)
                    if inventory is not None and not inventory.reserve(quantity):
                        raise ValidationError(
                            f"Stock insuffisant pour « {variant.product.name} » "
                            f"({variant.sku}). Disponible : {inventory.available()}."
                        )
                    order_item = OrderItem.objects.create(
                        order=order,
                        product_variant=variant,
                        quantity=quantity,
                        unit_price=variant.price,
                    )
                    subtotal += order_item.subtotal()
                order.total_amount = subtotal
                order.save(update_fields=["total_amount", "delivery_type"])
                items_total += subtotal

            global_order.items_total = items_total
            global_order.delivery_fee = delivery_fee
            global_order.total_amount = items_total + delivery_fee
            global_order.save(update_fields=["items_total", "delivery_fee", "total_amount"])

            # 3. Mission multi-collectes.
            delivery = Delivery.objects.create(global_order=global_order)
            total_distance = None
            coords_stores = [
                s for s in grouped
                if s.latitude is not None and s.longitude is not None
            ]
            order_map = {s.id: (i + 1) for i, s in enumerate(grouped.keys())}
            if coords_stores and address.latitude is not None and address.longitude is not None:
                total_distance = route_distance_km(coords_stores, address.latitude, address.longitude)
                driving_order = list(reversed(optimize_route(coords_stores, address.latitude, address.longitude)))
                order_map = {s.id: (i + 1) for i, s in enumerate(driving_order)}

            for store, lines in grouped.items():
                DeliveryPickup.objects.create(
                    delivery=delivery,
                    store=store,
                    seller=store.owner,
                    address=store.address,
                    city=store.city,
                    latitude=store.latitude,
                    longitude=store.longitude,
                    package_count=len(lines) or 1,
                    pickup_order=order_map.get(store.id, 1),
                )

            delivery.total_delivery_fee = delivery_fee
            delivery.total_distance = total_distance
            partner = best_delivery_partner(address)
            if partner is not None:
                delivery.partner_cost = partner.partner_cost_for(delivery)
                delivery.platform_margin = delivery_fee - delivery.partner_cost
                delivery.assign_partner(partner)
            else:
                delivery.platform_margin = delivery_fee
            delivery.save(update_fields=[
                "total_delivery_fee", "partner_cost", "platform_margin", "total_distance",
            ])

            # 4. Paiement unique.
            Payment.objects.create(
                global_order=global_order,
                amount=global_order.total_amount,
                method=payment_method,
            )

            # 5. Retrait des articles achetés du panier.
            CartItem.objects.filter(
                cart__user=request.user, product_variant_id__in=wants.keys()
            ).delete()

        from apps.analytics.models import SalesStatistic
        for order in global_order.orders.all():
            SalesStatistic.compute_for_store(order.store, order.created_at.date())

        return Response(GlobalOrderSerializer(global_order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Annule une commande encore annulable (client, boutique concernée ou admin)."""
        order = self.get_object()
        user = request.user
        is_allowed = (
            order.customer_id == user.id
            or order.store.owner_id == user.id
            or user.is_admin()
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


class DriverViewSet(viewsets.ModelViewSet):
    """
    Profils livreur : un admin voit tout, un commerçant voit les livreurs
    disponibles (pour affecter une livraison), un partenaire gère SES livreurs,
    un livreur ne voit que lui-même sauf via l'action `me`.

    Avec le paramètre `?store=<uuid>`, seuls les livreurs disponibles situés
    à moins de `DRIVER_ASSIGNMENT_RADIUS_KM` km de la boutique sont renvoyés
    (chacun avec sa `distance_km`), pour satisfaire la règle métier :
    un livreur ne peut récupérer une commande que s'il est près de la boutique.
    """
    serializer_class = DriverSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin():
            return Driver.objects.all()
        if user.has_role(Role.RoleName.PARTNER):
            return Driver.objects.filter(partner__user=user)
        if user.has_role(Role.RoleName.MERCHANT):
            return Driver.objects.filter(availability_status=Driver.AvailabilityStatus.AVAILABLE)
        return Driver.objects.filter(user=user)

    def list(self, request, *args, **kwargs):
        store_id = request.query_params.get("store")
        store = None
        if store_id and (
            request.user.is_admin() or request.user.has_role(Role.RoleName.MERCHANT)
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

    def create(self, request, *args, **kwargs):
        return self.register_driver(request)

    @action(detail=False, methods=["post"])
    def register(self, request):
        """Alias — l'inscription passe aussi par POST /drivers/register/."""
        return self.register_driver(request)

    @action(detail=False, methods=["post"], url_path="register")
    def register_driver(self, request):
        """Crée un compte livreur : un administrateur, ou un partenaire dans
        SA propre entreprise (spec §12). Nom, prénom, email, téléphone, type
        de véhicule. Le mot de passe provisoire est renvoyé une seule fois ;
        le livreur devra le changer à sa première connexion."""
        User = get_user_model()
        is_partner = request.user.has_role(Role.RoleName.PARTNER)
        if not request.user.is_admin() and not is_partner:
            raise PermissionDenied("Seul un administrateur ou un partenaire peut créer un compte livreur.")
        if is_partner:
            partner = DeliveryPartner.objects.filter(user=request.user).first()
            if partner is None:
                raise PermissionDenied("Aucune entreprise partenaire n'est liée à ce compte.")

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
        linked_partner = partner if is_partner else None
        partner_id = request.data.get("partner")
        if not is_partner and partner_id:
            linked_partner = DeliveryPartner.objects.filter(pk=partner_id).first()
        driver = Driver.objects.create(
            user=user,
            vehicle_type=vehicle_type,
            availability_status=Driver.AvailabilityStatus.OFFLINE,
            partner=linked_partner,
        )
        data = DriverSerializer(driver).data
        data["temporary_password"] = temporary_password
        return Response(data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        # Un partenaire ne peut modifier que les livreurs de son entreprise.
        user = self.request.user
        if user.has_role(Role.RoleName.PARTNER):
            partner = DeliveryPartner.objects.filter(user=user).first()
            if serializer.instance.partner_id != (partner.id if partner else None):
                raise PermissionDenied("Vous ne pouvez modifier que les livreurs de votre entreprise.")
        serializer.save()

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
    Livraisons : un livreur voit celles qui lui sont affectées, un partenaire
    celles de son entreprise, un commerçant celles de ses commandes, l'admin
    voit tout. La livraison elle-même est créée automatiquement par
    `OrderViewSet.checkout`, pas ici.
    """
    serializer_class = DeliverySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin():
            return Delivery.objects.all()
        if user.has_role(Role.RoleName.PARTNER):
            return Delivery.objects.filter(partner__user=user)
        if user.has_role(Role.RoleName.DRIVER):
            return Delivery.objects.filter(driver__user=user)
        return Delivery.objects.filter(
            models.Q(order__store__owner=user) | models.Q(global_order__orders__store__owner=user)
        ).distinct()

    def _partner_for(self, user):
        return DeliveryPartner.objects.filter(user=user).first()

    @action(detail=True, methods=["post"], url_path="suggest")
    def suggest_drivers(self, request, pk=None):
        """Renvoie les meilleurs livreurs candidats pour cette livraison
        (disponibles, non suspendus, proches de la boutique) — utilisé par
        l'Espace Partenaire pour proposer une affectation en un clic."""
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        if user.has_role(Role.RoleName.PARTNER):
            partner = self._partner_for(user)
            if delivery.partner_id != (partner.id if partner else None):
                raise PermissionDenied("Cette livraison n'appartient pas à votre entreprise.")
        elif not user.is_admin() and not (
            user.has_role(Role.RoleName.MERCHANT)
            and delivery.main_store() is not None
            and delivery.main_store().owner_id == user.id
        ):
            raise PermissionDenied("Vous ne pouvez pas consulter cette livraison.")
        suggested = delivery.suggested_driver(limit=int(request.query_params.get("limit", 5)))
        if suggested is None:
            return Response({"drivers": [], "message": "Aucun livreur disponible pour le moment."})
        return Response({
            "drivers": DriverSerializer(
                [suggested], many=True, context={"store": delivery.main_store()}
            ).data,
        })

    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request, pk=None):
        """Affecte un livreur : le commerçant, le partenaire (son entreprise)
        ou l'admin.

        Règle métier : le livreur doit se trouver à moins de
        `DRIVER_ASSIGNMENT_RADIUS_KM` km de la boutique — il doit être assez
        proche pour venir récupérer le colis avant de livrer le client.
        """
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        is_partner = user.has_role(Role.RoleName.PARTNER)
        partner = self._partner_for(user) if is_partner else None
        if not user.is_admin() and not (
            (is_partner and delivery.partner_id == (partner.id if partner else None))
            or (
                user.has_role(Role.RoleName.MERCHANT)
                and delivery.main_store() is not None
                and delivery.main_store().owner_id == user.id
            )
        ):
            raise PermissionDenied("Vous ne pouvez affecter un livreur qu'aux livraisons de votre entreprise.")
        driver = get_object_or_404(Driver, pk=request.data.get("driver"))
        if is_partner and driver.partner_id != (partner.id if partner else None):
            raise ValidationError("Vous ne pouvez affecter que des livreurs de votre entreprise.")

        store = delivery.main_store()
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

        delivery.assign_driver(driver, user=user)
        delivery.broadcast_status(
            f"Votre commande est prise en charge par {driver.user.get_full_name() or driver.user.email}."
        )
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=["post"], url_path="accept")
    def accept(self, request, pk=None):
        """Le livreur accepte la mission qui lui est affectée (§5, §8, §29)."""
        delivery = get_object_or_404(Delivery, pk=pk)
        try:
            delivery.accept(user=request.user)
        except PermissionError as exc:
            raise PermissionDenied(str(exc))
        except ValueError as exc:
            raise ValidationError(str(exc))
        delivery.broadcast_status("Mission acceptée par le livreur.")
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=["post"], url_path="refuse")
    def refuse(self, request, pk=None):
        """Le livreur refuse la mission avec un motif (spec §8) : la course
        redevient affectable et un autre livreur est proposé en priorité."""
        delivery = get_object_or_404(Delivery, pk=pk)
        reason = (request.data.get("reason") or "").strip()
        comment = (request.data.get("comment") or "").strip()
        if not reason:
            raise ValidationError("Un motif de refus est obligatoire.")
        try:
            delivery.refuse(user=request.user, reason=reason, comment=comment)
        except PermissionError as exc:
            raise PermissionDenied(str(exc))
        except ValueError as exc:
            raise ValidationError(str(exc))
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=["post"], url_path="collect-pickup")
    def collect_pickup(self, request, pk=None):
        """Le livreur marque un point de collecte comme récupéré (multi-boutiques).

        BODY : `{pickup: <uuid>}` (un DeliveryPickup de la mission).
        Règles : seul le livreur affecté (ou l'admin) ; les collectes suivent
        l'ordre (`pickup_order`) ; quand tous les colis requis sont récupérés,
        la course passe en `picked_up` et le client est prévenu.
        """
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        is_admin = user.is_admin()
        is_assigned_driver = delivery.driver and delivery.driver.user_id == user.id
        if not is_admin and not is_assigned_driver:
            raise PermissionDenied("Seul le livreur affecté peut valider une collecte.")
        if not delivery.is_multi_store:
            raise ValidationError("Cette livraison n'a pas de points de collecte multiples.")
        if delivery.status in (Delivery.Status.DELIVERED, Delivery.Status.CANCELLED):
            raise ValidationError("La course est déjà terminée.")

        pickup = get_object_or_404(
            DeliveryPickup, pk=request.data.get("pickup"), delivery=delivery
        )
        if pickup.pickup_status == DeliveryPickup.Status.PICKED_UP:
            raise ValidationError("Ce colis a déjà été récupéré.")
        if pickup.pickup_order > 1:
            previous = delivery.pickups.filter(
                pickup_order__lt=pickup.pickup_order
            ).exclude(pickup_status=DeliveryPickup.Status.PICKED_UP).order_by("pickup_order").first()
            if previous:
                raise ValidationError(
                    f"Le point de collecte n°{previous.pickup_order} "
                    f"(« {previous.store.name} ») doit être récupéré avant celui-ci."
                )

        pickup.pickup_status = DeliveryPickup.Status.PICKED_UP
        pickup.picked_up_at = timezone.now()
        pickup.save(update_fields=["pickup_status", "picked_up_at"])
        delivery.record_event(
            "pickup_collected", user=user,
            actor_role="driver" if not is_admin else "admin",
            comment=f"Colis récupéré : {pickup.store.name}",
            metadata={"pickup": str(pickup.id), "store": str(pickup.store_id)},
        )

        done, total, all_done = delivery.pickups_status()
        if all_done and delivery.status in (
            Delivery.Status.ASSIGNED, Delivery.Status.ACCEPTED, Delivery.Status.PICKUP_PENDING,
        ):
            delivery._transition_to(
                Delivery.Status.PICKED_UP, user=user, actor_role="driver",
                comment="Tous les colis sont récupérés.",
            )
            self._notify_customer_pickup(delivery)
            delivery.broadcast_status("Tous les colis sont récupérés : en route vers vous !")

        data = DeliverySerializer(delivery).data
        data["pickups_collected"] = done
        data["pickups_total"] = total
        return Response(data)

    @action(detail=True, methods=["post"], url_path="status")
    def update_status(self, request, pk=None):
        """Le livreur affecté (ou l'admin) fait progresser le statut de sa course.

        Chaîne 2025 (spec §5) : assigned → accepted → pickup_pending → picked_up
        → in_transit → out_for_delivery → delivered.

        La transition vers « livré » n'est PAS possible par le livreur via
        cette action : elle est validée par le client avec le code OTP
        (`confirm`), ou par un admin (dépannage).
        """
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        is_assigned_driver = delivery.driver and delivery.driver.user_id == user.id
        is_admin = user.is_admin()
        if not is_admin and not is_assigned_driver:
            raise PermissionDenied("Seul le livreur affecté peut mettre à jour cette livraison.")

        new_status = request.data.get("status")
        allowed_transitions = {
            Delivery.Status.ASSIGNED: [
                Delivery.Status.ACCEPTED, Delivery.Status.PICKED_UP,
                *([Delivery.Status.DELIVERED] if is_admin else []),
            ],
            Delivery.Status.ACCEPTED: [
                Delivery.Status.PICKUP_PENDING, Delivery.Status.PICKED_UP,
                *([Delivery.Status.DELIVERED] if is_admin else []),
            ],
            Delivery.Status.PICKUP_PENDING: [
                Delivery.Status.PICKED_UP,
                *([Delivery.Status.DELIVERED] if is_admin else []),
            ],
            Delivery.Status.PICKED_UP: [
                Delivery.Status.IN_TRANSIT,
                *([Delivery.Status.DELIVERED] if is_admin else []),
            ],
            Delivery.Status.IN_TRANSIT: [
                Delivery.Status.OUT_FOR_DELIVERY,
                *([Delivery.Status.DELIVERED] if is_admin else []),
            ],
            Delivery.Status.OUT_FOR_DELIVERY: [
                *([Delivery.Status.DELIVERED] if is_admin else []),
            ],
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
        self._stamp(delivery, new_status)
        delivery.save()
        delivery.record_event("status_changed", user=user, actor_role="driver" if not is_admin else "admin",
                              previous_status=delivery.status, new_status=new_status)

        if new_status == Delivery.Status.DELIVERED:
            for order in delivery.linked_orders():
                order.change_status(Order.Status.DELIVERED, changed_by=user)

        status_messages = {
            Delivery.Status.ASSIGNED: "Un livreur vous est affecté.",
            Delivery.Status.ACCEPTED: "Le livreur a accepté votre commande.",
            Delivery.Status.PICKUP_PENDING: "Le livreur se rend à la boutique.",
            Delivery.Status.PICKED_UP: "Le livreur a récupéré votre colis : en route !",
            Delivery.Status.IN_TRANSIT: "Votre colis est en route vers l'adresse de livraison.",
            Delivery.Status.OUT_FOR_DELIVERY: "Le livreur est à votre adresse : votre commande arrive !",
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
    def _stamp(delivery, new_status):
        stamps = {
            Delivery.Status.ACCEPTED: "accepted_at",
            Delivery.Status.PICKUP_PENDING: None,
            Delivery.Status.PICKED_UP: "picked_up_at",
            Delivery.Status.IN_TRANSIT: "in_transit_at",
            Delivery.Status.OUT_FOR_DELIVERY: "out_for_delivery_at",
            Delivery.Status.DELIVERED: "delivered_at",
        }
        field = stamps.get(new_status)
        if field:
            setattr(delivery, field, timezone.now())

    @action(detail=True, methods=["post"], url_path="fail")
    def fail(self, request, pk=None):
        """Le livreur signale un échec de livraison (§16-§17) : motif
        obligatoire + commentaire. La course passe en `delivery_failed` ou
        `customer_unavailable`, et une demande de retour peut être émise."""
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        is_assigned_driver = delivery.driver and delivery.driver.user_id == user.id
        if not user.is_admin() and not is_assigned_driver:
            raise PermissionDenied("Seul le livreur affecté peut signaler un échec.")
        if delivery.status not in [
            Delivery.Status.OUT_FOR_DELIVERY, Delivery.Status.IN_TRANSIT, Delivery.Status.PICKED_UP,
        ]:
            raise ValidationError("Échec impossible dans l'état actuel de la course.")
        delivery.mark_failed(
            user=user, actor_role="driver" if not is_admin else "admin",
            reason=request.data.get("reason"), comment=request.data.get("comment", ""),
        )
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=["post"], url_path="return")
    def request_return(self, request, pk=None):
        """Demande de retour du colis au vendeur (spec §18)."""
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        is_assigned_driver = delivery.driver and delivery.driver.user_id == user.id
        if not user.is_admin() and not is_assigned_driver:
            raise PermissionDenied("Seul le livreur affecté peut demander un retour.")
        delivery.request_return(
            user=user, actor_role="driver" if not is_assigned_driver else "driver",
            reason=request.data.get("reason"), comment=request.data.get("comment", ""),
        )
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=["post"], url_path="return/complete")
    def mark_returned(self, request, pk=None):
        """Le retour est terminé : le colis est rendu au vendeur (§18)."""
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        is_assigned_driver = delivery.driver and delivery.driver.user_id == user.id
        if not user.is_admin() and not is_assigned_driver:
            raise PermissionDenied("Seul le livreur affecté peut confirmer le retour.")
        delivery.mark_returned(user=user, actor_role="driver", comment=request.data.get("comment", ""))
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=["get"], url_path="events-history")
    def events_history(self, request, pk=None):
        """Timeline complète de la livraison (spec §28) pour l'Espace Partenaire/livreur."""
        delivery = self.get_object()
        events = delivery.events.select_related("actor").all()
        return Response(
            DeliveryEventSerializer(events, many=True).data
        )

    @staticmethod
    def _notify_customer_pickup(delivery):
        """Prévient le client que sa commande est en route (sans jamais
        transmettre le code OTP par email : il est remis en main propre
        par le livreur)."""
        from apps.monetization.models import Notification

        customer = delivery.target_customer()
        ref = delivery.order_id or delivery.global_order_id

        Notification.objects.create(
            user=customer,
            channel=Notification.Channel.EMAIL,
            subject="Votre colis est en route",
            message=(
                f"Bonjour,\n\n"
                f"Votre commande n°{str(ref)[:8]} est en cours de livraison.\n\n"
                "À la réception, le livreur vous communiquera un code de confirmation "
                "à saisir sur la page « Confirmer la livraison » pour valider votre commande.\n\n"
                "Merci de votre confiance."
            ),
            metadata={"delivery_id": str(delivery.id), "order_id": str(ref)},
        ).send()

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, pk=None):
        """Le client confirme la réception de sa commande avec le code OTP
        remis par le livreur (le destinataire ou un admin)."""
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        customer = delivery.target_customer()
        is_allowed = (customer is not None and customer.id == user.id) or user.is_admin()
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
        for order in delivery.linked_orders():
            order.change_status(Order.Status.DELIVERED, changed_by=user)
        delivery.broadcast_status("Livraison confirmée par le client. Bonne réception !")
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=["post"], url_path="regenerate-otp")
    def regenerate_otp(self, request, pk=None):
        """Le livreur affecté (ou l'admin) régénère le code de confirmation
        (code perdu, expiré, ou essais épuisés). L'ancien code est invalidé."""
        delivery = get_object_or_404(Delivery, pk=pk)
        user = request.user
        is_assigned_driver = delivery.driver and delivery.driver.user_id == user.id
        if not user.is_admin() and not is_assigned_driver:
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
        if not user.is_admin() and not is_assigned_driver:
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
        customer = delivery.target_customer()
        store = delivery.main_store()
        is_allowed = (
            (customer is not None and customer.id == user.id)
            or (store is not None and store.owner_id == user.id)
            or (delivery.driver_id and delivery.driver.user_id == user.id)
            or (delivery.partner_id and delivery.partner.user_id == user.id)
            or user.is_admin()
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


class GlobalOrderViewSet(viewsets.ReadOnlyModelViewSet):
    """Commandes globales multi-boutiques (spec multi-boutiques).

    - un client voit ses propres commandes globales ;
    - un commerçant voit les commandes globales où SA boutique figure ;
    - l'admin voit tout.

    La commande globale porte un paiement unique (`Payment.global_order`) ;
    ses sous-commandes ne sont visibles que par le vendeur concerné (isolation
    entre vendeurs, spec §11).
    """
    serializer_class = GlobalOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin():
            return GlobalOrder.objects.all()
        if user.has_role(Role.RoleName.MERCHANT):
            return GlobalOrder.objects.filter(orders__store__owner=user).distinct()
        return GlobalOrder.objects.filter(customer=user)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Annule une commande globale encore annulable (client ou admin).

        Toutes les sous-commandes annulables passent au statut CANCELLED, la
        course de livraison (si elle n'a pas déjà commencé) est annulée, et un
        remboursement est émis si le paiement global était déjà encaissé.
        """
        global_order = self.get_object()
        user = request.user
        if not (global_order.customer_id == user.id or user.is_admin()):
            raise PermissionDenied("Vous ne pouvez annuler que vos propres commandes.")
        if global_order.status == GlobalOrder.Status.CANCELLED:
            raise ValidationError("Cette commande a déjà été annulée.")

        delivery = global_order.deliveries.first()
        if delivery and delivery.status in (
            Delivery.Status.DELIVERED, Delivery.Status.DELIVERY_FAILED,
            Delivery.Status.CUSTOMER_UNAVAILABLE, Delivery.Status.RETURNED,
            Delivery.Status.CANCELLED,
        ):
            raise ValidationError(
                f"La course est au statut « {delivery.status} » : annulation impossible."
            )

        with transaction.atomic():
            for order in global_order.orders.all():
                if order.can_be_cancelled():
                    order.change_status(Order.Status.CANCELLED, changed_by=user)
            if delivery and delivery.status in (
                Delivery.Status.PENDING, Delivery.Status.ASSIGNED, Delivery.Status.ACCEPTED,
            ):
                delivery.cancel(user=user)
            global_order.status = GlobalOrder.Status.CANCELLED
            global_order.save(update_fields=["status"])

        payment = global_order.payments.filter(status=Payment.Status.SUCCESS).first()
        if payment:
            Refund.objects.create(
                payment=payment,
                amount=payment.amount,
                reason="Commande globale annulée",
            )

        return Response(GlobalOrderSerializer(global_order).data)


class DeliveryPricingRuleViewSet(viewsets.ReadOnlyModelViewSet):
    """Règles de tarification livraison (admin uniquement, spec §7-§8).

    L'administration ajuste les montants (base, point de collecte
    supplémentaire, km, express, min/max) — le moteur de calcul lit toujours
    la règle active ; aucun montant n'est codé en dur. Un singleton actif est
    créé par défaut au premier calcul.
    """
    queryset = DeliveryPricingRule.objects.all()
    serializer_class = DeliveryPricingRuleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT", "POST", "DELETE"):
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]


class PartnerViewSet(viewsets.ModelViewSet):
    """Gestion administrative des entreprises partenaires (admin uniquement).

    - Création, lecture, mise à jour, suspension des partenaires.
    - `activate` / `suspend` : bascule du statut opérationnel.
    - `rotate-api-key` : régénère la clé d'API d'intégration du partenaire.
    """

    queryset = DeliveryPartner.objects.all().order_by("-created_at")
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return DeliveryPartnerDetailSerializer
        return DeliveryPartnerSerializer

    def get_queryset(self):
        if not self.request.user.is_admin():
            raise PermissionDenied("Seul un administrateur gère les entreprises partenaires.")
        return super().get_queryset()

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        partner = self.get_object()
        partner.status = DeliveryPartner.Status.ACTIVE
        partner.save()
        return Response(DeliveryPartnerDetailSerializer(partner).data)

    @action(detail=True, methods=["post"], url_path="suspend")
    def suspend(self, request, pk=None):
        partner = self.get_object()
        partner.status = DeliveryPartner.Status.SUSPENDED
        partner.save()
        return Response(DeliveryPartnerDetailSerializer(partner).data)

    @action(detail=True, methods=["post"], url_path="rotate-api-key")
    def rotate_api_key(self, request, pk=None):
        partner = self.get_object()
        raw = partner.rotate_api_key()
        return Response({"api_key": raw, "api_key_last4": partner.api_key_last4})


class PartnerSpaceViewSet(viewsets.ViewSet):
    """Espace Partenaire : l'utilisateur `partner` pilote son entreprise.

    Routes :
    - GET  /api/orders/partner/profile/        → profil de l'entreprise
    - PATCH /api/orders/partner/profile/       → mise à jour du profil
    - POST /api/orders/partner/api-key/        → rotation clé d'API
    - GET  /api/orders/partner/stats/          → tableau de bord (spec §6)
    - GET  /api/orders/partner/deliveries/     → livraisons (filtres si trouvés)
    - GET  /api/orders/partner/invoices/       → factures (spec §19-§22)
    - GET  /api/orders/partner/invoices/<pk>/  → détail + délai de paiement
    - GET  /api/orders/partner/zones/          → tarifs par zone
    - PATCH /api/orders/partner/zones/<pk>/    → ajuster un tarif zone
    """
    permission_classes = [permissions.IsAuthenticated]

    def _partner(self, request):
        partner = DeliveryPartner.objects.filter(user=request.user).first()
        if partner is None:
            raise NotFound("Aucune entreprise partenaire n'est liée à votre compte.")
        return partner

    def profile(self, request):
        partner = self._partner(request)
        if request.method == "PATCH":
            serializer = DeliveryPartnerSerializer(partner, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(DeliveryPartnerDetailSerializer(partner).data)

    def api_key(self, request):
        partner = self._partner(request)
        raw = partner.rotate_api_key()
        return Response({"api_key": raw, "api_key_last4": partner.api_key_last4})

    def banks(self, request):
        """Moyens de paiement du partenaire (affichage) — complétion §12 monétique."""
        partner = self._partner(request)
        return Response({"method": "bank_transfer", "iban": "", "provider": ""})

    def stats(self, request):
        partner = self._partner(request)
        today = timezone.localdate()
        month_start = today.replace(day=1)
        deliveries = partner.deliveries

        def _count(qs):
            return qs.count()

        active = deliveries.exclude(
            status__in=[
                Delivery.Status.DELIVERED, Delivery.Status.DELIVERY_FAILED,
                Delivery.Status.CUSTOMER_UNAVAILABLE, Delivery.Status.RETURNED,
                Delivery.Status.CANCELLED,
            ]
        )
        month_deliveries = deliveries.filter(created_at__date__gte=month_start)
        total_revenue = sum(
            (d.partner_cost_for(d) for d in deliveries.filter(status=Delivery.Status.DELIVERED)),
            Decimal("0"),
        )
        unpaid_amount = sum(
            (inv.balance for inv in partner.invoices.filter(status=PartnerInvoice.Status.PENDING)),
            Decimal("0"),
        )
        return Response({
            "period_start": today.isoformat(),
            "deliveries_total": _count(deliveries),
            "deliveries_in_progress": _count(active),
            "deliveries_delivered": _count(deliveries.filter(status=Delivery.Status.DELIVERED)),
            "deliveries_failed": _count(deliveries.filter(
                status__in=[Delivery.Status.DELIVERY_FAILED, Delivery.Status.CUSTOMER_UNAVAILABLE]
            )),
            "deliveries_returned": _count(deliveries.filter(status__in=[
                Delivery.Status.RETURN_REQUESTED, Delivery.Status.RETURNED,
            ])),
            "deliveries_month": _count(month_deliveries),
            "success_rate": partner.success_rate(),
            "return_rate": partner.return_rate(),
            "avg_delay_minutes": partner.avg_delay_minutes(),
            "active_drivers": partner.active_drivers().count(),
            "total_revenue": str(total_revenue),
            "unpaid_amount": str(unpaid_amount),
        })

    def deliveries(self, request):
        partner = self._partner(request)
        qs = partner.deliveries.select_related("order", "order__store", "driver", "driver__user")
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(DeliverySerializer(qs, many=True).data)

    def invoices(self, request):
        partner = self._partner(request)
        return Response(PartnerInvoiceSerializer(partner.invoices.all(), many=True).data)

    def invoice_detail(self, request, pk=None):
        partner = self._partner(request)
        invoice = get_object_or_404(partner.invoices, pk=pk)
        return Response(PartnerInvoiceSerializer(invoice).data)

    def zones(self, request):
        partner = self._partner(request)
        return Response(PartnerZonePricingSerializer(partner.zone_pricings.all(), many=True).data)

    def zone_update(self, request, pk=None):
        partner = self._partner(request)
        zp = get_object_or_404(partner.zone_pricings, pk=pk)
        serializer = PartnerZonePricingSerializer(zp, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
