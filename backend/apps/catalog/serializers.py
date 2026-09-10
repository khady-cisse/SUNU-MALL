import uuid

from rest_framework import serializers
from .models import Category, Inventory, Product, ProductImage, ProductVariant, Review, Store, StoreCategory, StoreSettings
from apps.kyc.models import SellerKYC


class CategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "parent", "name", "image_url", "created_at", "updated_at"]
        read_only_fields = ["id", "image_url", "created_at", "updated_at"]

    def get_image_url(self, obj):
        return obj.image.url if obj.image else None


class StoreCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreCategory
        fields = ["id", "name"]
        read_only_fields = ["id"]


class ProductImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "url", "position", "created_at"]

    def get_url(self, obj):
        return obj.get_signed_url() or None


class StoreSerializer(serializers.ModelSerializer):
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()
    category_detail = StoreCategorySerializer(source='category', read_only=True)
    # Alimentés par l'annotation Subquery de StoreViewSet.get_queryset (moyenne
    # des notes / nombre d'avis réels sur les produits de la boutique) —
    # absents (None) si la vue qui a produit l'instance ne les a pas annotés.
    rating = serializers.FloatField(read_only=True, default=None)
    review_count = serializers.IntegerField(read_only=True, default=0)
    category_names = serializers.SerializerMethodField()
    # Badge "Vendeur vérifié" généré BACKEND (spec §9) : l'annotation
    # Exists le fournit sur les querysets de liste ; sinon le champ se calcule
    # à la volée pour un objet isolé.
    is_verified_seller = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            "id", "owner", "owner_email", "category", "category_detail", "name",
            "phone", "description", "address", "city", "rejection_reason",
            "logo_url", "banner_url", "status", "latitude", "longitude", "rating", "review_count",
            "category_names", "is_verified_seller",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "owner", "created_at", "updated_at", "owner_email",
            "logo_url", "banner_url", "category_detail", "rejection_reason",
        ]

    def get_logo_url(self, obj):
        return obj.logo.url if obj.logo else None

    def get_banner_url(self, obj):
        return obj.banner.url if obj.banner else None

    def get_category_names(self, obj):
        # .order_by() vide avant .distinct() : sans ça, le tri par défaut de
        # Product (Meta.ordering = ['-created_at']) s'invite dans le SQL et
        # empêche la déduplication (chaque produit garde sa propre ligne).
        return list(
            obj.products.filter(status=Product.Status.ACTIVE, category__isnull=False)
            .order_by()
            .values_list("category__name", flat=True)
            .distinct()
        )

    def get_is_verified_seller(self, obj):
        annotated = getattr(obj, "is_verified_seller", None)
        if annotated is not None:
            return annotated
        return SellerKYC.objects.filter(
            seller_id=obj.owner_id, status=SellerKYC.Status.VERIFIED,
        ).exists()


class StoreSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreSettings
        fields = ["id", "store", "business_hours", "min_order_amount", "created_at", "updated_at"]
        read_only_fields = ["id", "store", "created_at", "updated_at"]


class ProductVariantSerializer(serializers.ModelSerializer):
    is_available = serializers.SerializerMethodField()
    quantity = serializers.SerializerMethodField()
    initial_quantity = serializers.IntegerField(write_only=True, required=False, default=100, min_value=0)
    # Référence interne facultative : si absente ou vide, un code unique est
    # généré automatiquement (le vendeur ne connaît pas forcément le concept de SKU).
    sku = serializers.CharField(required=False, allow_blank=True, max_length=100)

    class Meta:
        model = ProductVariant
        fields = [
            "id", "product", "sku", "attributes", "price",
            "is_available", "quantity", "initial_quantity",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "is_available", "quantity", "created_at", "updated_at"]

    def get_is_available(self, obj):
        return obj.is_available()

    def get_quantity(self, obj):
        return obj.inventory.available() if hasattr(obj, "inventory") else 0

    def _generate_sku(self, product_id):
        for _ in range(5):
            candidate = f"P{product_id}-{uuid.uuid4().hex[:6].upper()}"
            if not ProductVariant.objects.filter(sku=candidate).exists():
                return candidate
        return f"P{product_id}-{uuid.uuid4().hex[:12].upper()}"

    def create(self, validated_data):
        initial_quantity = validated_data.pop("initial_quantity", 100)
        if not (validated_data.get("sku") or "").strip():
            validated_data["sku"] = self._generate_sku(validated_data["product"].id)
        variant = super().create(validated_data)
        Inventory.objects.create(variant=variant, quantity=initial_quantity)
        return variant


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = Review
        fields = ["id", "product", "user", "user_name", "rating", "comment", "created_at"]
        read_only_fields = ["id", "user", "user_name", "created_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        if request and request.method == "POST":
            product = attrs.get("product")
            if product and Review.objects.filter(product=product, user=request.user).exists():
                raise serializers.ValidationError("Vous avez déjà laissé un avis pour ce produit.")
        return attrs


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    store_name = serializers.CharField(source='store.name', read_only=True)
    # Badge boutique "vendeur vérifié" sur la tuile produit (spec §9) — même
    # mécanique que StoreSerializer.is_verified_seller.
    store_is_verified = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "store", "store_name", "store_is_verified", "category", "brand", "name", "description",
            "base_price", "status", "images", "variants",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_store_is_verified(self, obj):
        annotated = getattr(obj, "store_is_verified", None)
        if annotated is not None:
            return annotated
        return SellerKYC.objects.filter(
            seller_id=obj.store.owner_id, status=SellerKYC.Status.VERIFIED,
        ).exists()
