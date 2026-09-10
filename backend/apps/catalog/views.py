from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.db import models
from django.db.models.functions import Coalesce
from django.utils import timezone
from .models import Category, Product, ProductImage, ProductVariant, Review, Store, StoreCategory, StoreSettings
from .serializers import (
    CategorySerializer, ProductImageSerializer, ProductSerializer, ProductVariantSerializer,
    ReviewSerializer, StoreCategorySerializer, StoreSerializer, StoreSettingsSerializer,
)
from apps.users.permissions import IsAdmin, IsStoreOwnerOrAdmin
from apps.monetization.models import Notification, Subscription, SubscriptionPlan, SponsoredProduct
from apps.kyc.models import SellerKYC
from apps.kyc.utils import seller_account_active, seller_kyc_verified
from apps.monetization import services as monetization_services
from apps.monetization.services import PRODUCT_LIMIT_EXCEEDED_MESSAGE


def _active_product_limit(store):
    """
    Nombre max de produits autorisés pour la boutique, selon l'abonnement en
    cours de son propriétaire — None = illimité, 0 = pas d'abonnement actif.
    Calcul côté backend uniquement (source de vérité, spec monétisation §10).
    """
    return monetization_services.product_limit_for(store.owner)


def _check_product_limit(store, exclude_product_id=None):
    from rest_framework.exceptions import ValidationError

    limit = _active_product_limit(store)
    if limit is None:
        return
    if limit == 0:
        raise ValidationError(
            "Vous n'avez pas d'abonnement actif. Souscrivez à une formule pour publier des produits."
        )
    count = Product.objects.filter(store=store)
    if exclude_product_id:
        count = count.exclude(id=exclude_product_id)
    if count.count() >= limit:
        raise ValidationError(PRODUCT_LIMIT_EXCEEDED_MESSAGE)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = []

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy", "upload_image"]:
            return [permissions.IsAuthenticated(), IsAdmin()]
        return super().get_permissions()

    @action(detail=False, methods=["get"], url_path="store-counts")
    def store_counts(self, request):
        """
        GET /api/catalog/categories/store-counts/
        Nombre de boutiques actives ayant au moins un produit actif dans
        chaque catégorie — pour le filtre par catégorie de la page
        boutiques. N'affiche que les catégories réellement représentées
        (aucune catégorie vide inventée).
        """
        categories = (
            Category.objects.annotate(
                store_count=models.Count(
                    "products__store",
                    filter=models.Q(products__status=Product.Status.ACTIVE, products__store__status=Store.Status.ACTIVE),
                    distinct=True,
                )
            )
            .filter(store_count__gt=0)
            .order_by("name")
        )
        return Response([{"id": c.id, "name": c.name, "store_count": c.store_count} for c in categories])

    @action(
        detail=True,
        methods=["post"],
        url_path="image",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_image(self, request, pk=None):
        """Visuel de la tuile de catégorie (accueil, page catégories). Admin uniquement."""
        category = self.get_object()
        image_file = request.FILES.get("image")
        if not image_file:
            return Response({"error": "Fichier 'image' requis."}, status=status.HTTP_400_BAD_REQUEST)
        category.image = image_file
        category.save(update_fields=["image"])
        return Response(CategorySerializer(category).data)


class StoreCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Catégories de boutique (Électronique, Mode, ...) — lecture publique, pour le formulaire de création de boutique."""
    queryset = StoreCategory.objects.all().order_by("name")
    serializer_class = StoreCategorySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class ProductViewSet(viewsets.ModelViewSet):
    """
    Lecture publique (un acheteur doit pouvoir parcourir le catalogue
    sans être connecté), écriture réservée aux utilisateurs authentifiés
    (à affiner : un vendeur ne devrait modifier que ses propres produits).
    """

    queryset = Product.objects.filter(status=Product.Status.ACTIVE)
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["store", "category", "status"]
    search_fields = ["name", "description"]

    def get_permissions(self):
        # La lecture (list/retrieve/sponsored) reste publique ; seules les
        # actions qui modifient un produit précis exigent d'en être propriétaire.
        if self.action in ["update", "partial_update", "destroy", "upload_image", "delete_image"]:
            return [permissions.IsAuthenticated(), IsStoreOwnerOrAdmin()]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.is_admin():
            queryset = Product.objects.all()
        elif user.is_authenticated:
            queryset = Product.objects.filter(models.Q(status=Product.Status.ACTIVE) | models.Q(store__owner=user))
        else:
            queryset = Product.objects.filter(status=Product.Status.ACTIVE)

        if self.request.query_params.get("sponsored") == "true":
            today = timezone.now().date()
            sponsored_product_ids = SponsoredProduct.objects.filter(
                status=SponsoredProduct.Status.ACTIVE,
                starts_at__lte=today,
                ends_at__gte=today,
            ).values_list("product_id", flat=True)
            queryset = queryset.filter(id__in=sponsored_product_ids)

        # Éviter les N+1 : ProductSerializer sérialise images + variants, et
        # ProductVariantSerializer lit inventory (get_quantity / is_available).
        # Prefetch les trois en 2 requêtes au lieu d'1 par produit/variante.
        # Badge boutique vérifiée : une seule sous-requête Exists agrégée.
        return queryset.annotate(
            store_is_verified=models.Exists(
                SellerKYC.objects.filter(
                    seller_id=models.OuterRef("store__owner_id"),
                    status=SellerKYC.Status.VERIFIED,
                )
            )
        ).prefetch_related(
            "images",
            models.Prefetch(
                "variants",
                queryset=ProductVariant.objects.select_related("inventory"),
            ),
        )

    def perform_create(self, serializer):
        store = serializer.validated_data.get("store")
        user = self.request.user
        if not user.is_admin() and store.owner_id != user.id:
            raise PermissionDenied("Vous ne pouvez ajouter des produits que dans votre propre boutique.")
        # Limite de produits appliquée à la CRÉATION (spec monétisation §10) :
        # comptage backend de tous les produits de la boutique, pas seulement
        # les actifs — le client n'est jamais autorisé à décider de la limite.
        if not user.is_admin():
            _check_product_limit(store)
        if serializer.validated_data.get("status") == Product.Status.ACTIVE:
            # Gating KYC (spec §8, §21) : publier un produit exige une identité
            # vérifiée — et non suspendue/bloquée.
            if not user.is_admin() and not seller_account_active(user):
                raise PermissionDenied(
                    "Votre identité (KYC) doit être vérifiée pour publier un produit."
                )
        serializer.save()

    def perform_update(self, serializer):
        product = self.get_object()
        new_status = serializer.validated_data.get("status")
        # Ne vérifie que le passage draft/inactive → active : modifier un
        # produit déjà actif (prix, description...) ne doit jamais être
        # bloqué par la limite de son offre.
        if new_status == Product.Status.ACTIVE and product.status != Product.Status.ACTIVE:
            _check_product_limit(product.store, exclude_product_id=product.id)
            user = self.request.user
            if not user.is_admin() and not seller_account_active(user):
                raise PermissionDenied(
                    "Votre identité (KYC) doit être vérifiée pour publier un produit."
                )
        serializer.save()

    @action(
        detail=True,
        methods=["post"],
        url_path="images",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_image(self, request, pk=None):
        """Upload d'une photo produit (multipart/form-data, champ 'image') vers MinIO."""
        product = self.get_object()
        image_file = request.FILES.get("image")
        if not image_file:
            return Response({"error": "Fichier 'image' requis."}, status=status.HTTP_400_BAD_REQUEST)
        position = product.images.count()
        product_image = ProductImage.objects.create(product=product, image=image_file, position=position)
        return Response(ProductImageSerializer(product_image).data, status=status.HTTP_201_CREATED)

    @upload_image.mapping.delete
    def delete_image(self, request, pk=None):
        product = self.get_object()
        image_id = request.query_params.get("image_id")
        image = get_object_or_404(ProductImage, pk=image_id, product=product)
        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], permission_classes=[permissions.AllowAny])
    def sponsored(self, request):
        """
        Produits actuellement mis en avant (campagne de sponsoring active),
        accessible publiquement pour alimenter les carrousels "Sponsorisé"
        de la marketplace (accueil, résultats de recherche, etc.).
        """
        today = timezone.now().date()
        sponsored_product_ids = SponsoredProduct.objects.filter(
            status=SponsoredProduct.Status.ACTIVE,
            starts_at__lte=today,
            ends_at__gte=today,
        ).values_list("product_id", flat=True)
        queryset = self.get_queryset().filter(id__in=sponsored_product_ids)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], permission_classes=[permissions.AllowAny])
    def best_sellers(self, request):
        """
        Produits les plus vendus (quantité totale commandée sur des
        commandes non annulées), pour un rail "Meilleures ventes" sur
        la marketplace. Public, comme `sponsored`. Avec ?store=<id>,
        restreint le classement aux produits de cette boutique (utilisé
        par l'onglet Analytics du commerçant pour son propre top produits).
        """
        from apps.orders.models import Order, OrderItem

        items = OrderItem.objects.exclude(order__status=Order.Status.CANCELLED)
        store_id = request.query_params.get("store")
        if store_id:
            items = items.filter(product_variant__product__store_id=store_id)

        ranking = list(
            items
            .values("product_variant__product_id")
            .annotate(total_qty=models.Sum("quantity"))
            .order_by("-total_qty")[:12]
        )
        qty_by_id = {str(row["product_variant__product_id"]): row["total_qty"] for row in ranking}
        top_product_ids = [row["product_variant__product_id"] for row in ranking]

        # `filter(id__in=...)` ne préserve pas l'ordre de popularité : on le
        # ré-applique nous-mêmes après coup.
        products_by_id = {p.id: p for p in self.get_queryset().filter(id__in=top_product_ids)}
        ordered = [products_by_id[pid] for pid in top_product_ids if pid in products_by_id]
        serializer = self.get_serializer(ordered, many=True)
        data = serializer.data
        for item in data:
            item["sold_quantity"] = qty_by_id.get(item["id"])
        return Response(data)

    @action(detail=True, methods=["get"], permission_classes=[permissions.AllowAny])
    def similar(self, request, pk=None):
        """
        Produits fréquemment achetés dans les mêmes commandes que celui-ci
        (co-achat, à partir des commandes réelles non annulées) — un
        agrégat SQL classique, pas un appel IA générative : instantané et
        gratuit, contrairement à un appel LLM par affichage de page produit.
        Si le co-achat ne donne pas assez de résultats (produit encore peu
        vendu), complète avec d'autres produits actifs de la même catégorie.
        """
        from apps.orders.models import Order, OrderItem

        product = self.get_object()

        order_ids = (
            OrderItem.objects.filter(product_variant__product=product)
            .exclude(order__status=Order.Status.CANCELLED)
            .values_list("order_id", flat=True)
        )
        co_purchased_ids = list(
            OrderItem.objects.filter(order_id__in=order_ids)
            .exclude(product_variant__product=product)
            .values("product_variant__product_id")
            .annotate(freq=models.Count("id"))
            .order_by("-freq")
            .values_list("product_variant__product_id", flat=True)[:12]
        )

        products_by_id = {p.id: p for p in self.get_queryset().filter(id__in=co_purchased_ids)}
        ordered = [products_by_id[pid] for pid in co_purchased_ids if pid in products_by_id]

        if len(ordered) < 8 and product.category_id:
            exclude_ids = {product.id, *(p.id for p in ordered)}
            same_category = (
                self.get_queryset()
                .filter(category_id=product.category_id)
                .exclude(id__in=exclude_ids)
                .order_by("-created_at")[: 8 - len(ordered)]
            )
            ordered.extend(same_category)

        serializer = self.get_serializer(ordered, many=True)
        return Response(serializer.data)

class ProductVariantViewSet(viewsets.ModelViewSet):
    """
    Variantes d'un produit (SKU, prix, attributs). Lecture publique pour
    permettre au panier de résoudre un product_variant ; écriture réservée
    au propriétaire de la boutique (à affiner avec une permission dédiée
    une fois le flux de gestion produit stabilisé côté frontend).
    """

    queryset = ProductVariant.objects.all()
    serializer_class = ProductVariantSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["product"]

    def get_permissions(self):
        if self.action in ["update", "partial_update", "destroy"]:
            return [permissions.IsAuthenticated(), IsStoreOwnerOrAdmin()]
        return super().get_permissions()

    def perform_create(self, serializer):
        product = serializer.validated_data.get("product")
        user = self.request.user
        if not user.is_admin() and product.store.owner_id != user.id:
            raise PermissionDenied("Vous ne pouvez ajouter des variantes qu'à vos propres produits.")
        serializer.save()


class StoreViewSet(viewsets.ModelViewSet):
    """
    Lecture publique des boutiques actives (un client doit pouvoir parcourir
    les boutiques sans être connecté) ; un commerçant voit en plus ses propres
    boutiques quel que soit leur statut ; l'admin voit tout et seul l'admin
    peut approuver/rejeter.
    """
    serializer_class = StoreSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "owner"]
    search_fields = ["name"]
    ordering_fields = ["created_at", "name", "rating"]
    ordering = ["-created_at"]

    def get_permissions(self):
        if self.action in ["approve", "reject"]:
            return [permissions.IsAuthenticated(), IsAdmin()]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.is_admin():
            qs = Store.objects.all()
        elif user.is_authenticated:
            qs = Store.objects.filter(models.Q(status=Store.Status.ACTIVE) | models.Q(owner=user))
        else:
            qs = Store.objects.filter(status=Store.Status.ACTIVE)

        # Sous-requêtes indépendantes (plutôt qu'un simple .annotate(Avg(...))
        # sur le queryset principal) : le filtre product_category ci-dessous
        # joint aussi via `products`, et cumuler les deux joins gonflerait
        # artificiellement la moyenne/le compte d'avis (fan-out de jointure).
        review_qs = Review.objects.filter(product__store=models.OuterRef("pk"))
        rating_subquery = review_qs.values("product__store").annotate(avg=models.Avg("rating")).values("avg")
        count_subquery = review_qs.values("product__store").annotate(cnt=models.Count("id")).values("cnt")
        qs = qs.annotate(
            rating=models.Subquery(rating_subquery[:1], output_field=models.FloatField()),
            review_count=Coalesce(
                models.Subquery(count_subquery[:1], output_field=models.IntegerField()), 0
            ),
            # Badge "Vendeur vérifié" : une sous-requête Exists, zéro coût par
            # page (une seule jointure agrégée, pas de boucle par boutique).
            is_verified_seller=models.Exists(
                SellerKYC.objects.filter(seller_id=models.OuterRef("owner_id"),
                                         status=SellerKYC.Status.VERIFIED)
            ),
        )

        category_id = self.request.query_params.get("product_category")
        if category_id:
            qs = qs.filter(products__category_id=category_id, products__status=Product.Status.ACTIVE).distinct()

        return qs

    def perform_create(self, serializer):
        # Gating KYC (spec §21) : un vendeur ne peut ouvrir de boutique que si
        # son identité (SellerKYC) a été vérifiée par l'administration.
        if not seller_kyc_verified(self.request.user):
            raise PermissionDenied(
                "Votre identité (KYC) doit être vérifiée par un administrateur "
                "avant de pouvoir créer une boutique."
            )
        # Règle « 1 vendeur = 1 boutique » (spec §1) : appliquée côté backend,
        # jamais dans le frontend. Un commerçant ne peut posséder qu'une seule
        # boutique, quel que soit son statut (active, en attente, suspendue) —
        # il la supprime d'abord s'il veut repartir de zéro. L'admin reste libre
        # (un admin peut créer une boutique pour un vendeur via l'administration).
        if not self.request.user.is_admin() and Store.objects.filter(
            owner=self.request.user
        ).exists():
            raise PermissionDenied(
                "Vous avez déjà une boutique sur Sunu Mall : 1 vendeur = 1 boutique. "
                "Modifiez votre boutique existante ou supprimez-la pour en créer une nouvelle."
            )
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        store = self.get_object()
        user = self.request.user
        if not user.is_admin() and store.owner_id != user.id:
            raise PermissionDenied("Vous ne pouvez modifier que votre propre boutique.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not user.is_admin() and instance.owner_id != user.id:
            raise PermissionDenied("Vous ne pouvez supprimer que votre propre boutique.")
        instance.delete()

    @action(
        detail=True,
        methods=["post"],
        url_path="logo",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_logo(self, request, pk=None):
        """Photo de profil de la boutique — réservée au propriétaire (ou à l'admin)."""
        store = self.get_object()
        user = request.user
        if not user.is_admin() and store.owner_id != user.id:
            raise PermissionDenied("Vous ne pouvez modifier que votre propre boutique.")
        image_file = request.FILES.get("logo")
        if not image_file:
            return Response({"error": "Fichier 'logo' requis."}, status=status.HTTP_400_BAD_REQUEST)
        store.logo = image_file
        store.save(update_fields=["logo"])
        return Response(StoreSerializer(store).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="banner",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_banner(self, request, pk=None):
        """Photo de couverture de la boutique — réservée au propriétaire (ou à l'admin)."""
        store = self.get_object()
        user = request.user
        if not user.is_admin() and store.owner_id != user.id:
            raise PermissionDenied("Vous ne pouvez modifier que votre propre boutique.")
        image_file = request.FILES.get("banner")
        if not image_file:
            return Response({"error": "Fichier 'banner' requis."}, status=status.HTTP_400_BAD_REQUEST)
        store.banner = image_file
        store.save(update_fields=["banner"])
        return Response(StoreSerializer(store).data)

    def _notify_owner(self, store, subject, message):
        notification = Notification.objects.create(
            user=store.owner,
            channel=Notification.Channel.EMAIL,
            subject=subject,
            message=message,
            metadata={"store_id": str(store.id), "store_status": store.status},
        )
        notification.send()

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        store = self.get_object()
        store.status = Store.Status.ACTIVE
        store.rejection_reason = ""
        store.save()
        subject = f"Boutique '{store.name}' approuvée"
        message = (
            f"Bonjour {store.owner.first_name},\n\n"
            f"Votre boutique '{store.name}' a été approuvée et est maintenant active sur SUNU MALL.\n\n"
            "Merci pour votre patience."
        )
        self._notify_owner(store, subject, message)
        serializer = self.get_serializer(store)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        store = self.get_object()
        reason = request.data.get("reason", "Votre boutique n'a pas été validée.")
        store.status = Store.Status.SUSPENDED
        store.rejection_reason = reason
        store.save()
        subject = f"Boutique '{store.name}' rejetée"
        message = (
            f"Bonjour {store.owner.first_name},\n\n"
            f"Votre boutique '{store.name}' a été rejetée.\n"
            f"Raison : {reason}\n\n"
            "Merci de corriger les informations et de soumettre à nouveau."
        )
        self._notify_owner(store, subject, message)
        serializer = self.get_serializer(store)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get", "patch"], url_path="settings")
    def settings_endpoint(self, request, pk=None):
        """
        Paramètres de la boutique (horaires, montant minimum de commande),
        créés à la volée s'ils n'existent pas encore. Réservé au
        propriétaire de la boutique (ou à l'admin) — une boutique active
        reste visible en lecture publique via `get_queryset`, mais ses
        paramètres ne doivent être modifiables que par son propriétaire.
        """
        store = self.get_object()
        if not request.user.is_admin() and store.owner_id != request.user.id:
            raise PermissionDenied("Vous ne pouvez consulter/modifier que les paramètres de votre propre boutique.")
        settings_obj, _ = StoreSettings.objects.get_or_create(store=store)
        if request.method == "PATCH":
            serializer = StoreSettingsSerializer(settings_obj, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(StoreSettingsSerializer(settings_obj).data)


class ReviewViewSet(viewsets.ModelViewSet):
    """
    Avis produits (note 1-5 + commentaire) : lecture publique pour afficher
    les avis sur la fiche produit, écriture réservée à l'auteur de l'avis
    (ou à l'admin) — un même utilisateur ne peut laisser qu'un avis par
    produit (contrainte unique_together côté modèle).
    """
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["product"]

    def get_queryset(self):
        if self.action in ["update", "partial_update", "destroy"]:
            user = self.request.user
            if user.is_authenticated and user.is_admin():
                return Review.objects.all()
            return Review.objects.filter(user=user)
        return Review.objects.all()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
