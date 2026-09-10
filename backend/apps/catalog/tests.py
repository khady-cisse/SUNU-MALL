"""
Tests pour la propriété des produits (permissions) et l'upload d'images.

Les tests d'upload utilisent un stockage fichier local temporaire plutôt que
MinIO : ils vérifient le comportement de l'application (permissions,
création de l'objet ProductImage), pas la disponibilité d'une vraie
infrastructure S3 — ce qui les rend exécutables tel quel en CI.
"""
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient
from apps.users.models import User, Role, UserRole
from apps.catalog.models import Product, ProductVariant, Store
from apps.kyc.models import SellerKYC

# 1x1 PNG transparent minimal, valide pour Pillow.
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

_TMP_MEDIA_ROOT = tempfile.mkdtemp(prefix="sunu-mall-test-media-")


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    MEDIA_ROOT=_TMP_MEDIA_ROOT,
)
class CatalogOwnershipTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_TMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        Role.objects.get_or_create(name=Role.RoleName.MERCHANT)

        self.owner = self._make_merchant("owner@example.com")
        self.other = self._make_merchant("other@example.com")

        self.store = Store.objects.create(owner=self.owner, name="Ma boutique")
        self.product = Product.objects.create(store=self.store, name="Produit", base_price=1000)

    def _make_merchant(self, email):
        user = User.objects.create_user(username=email, email=email, password="testpass123", is_verified=True)
        role = Role.objects.get(name=Role.RoleName.MERCHANT)
        UserRole.objects.create(user=user, role=role)
        return user

    def _verify_kyc(self, user):
        return SellerKYC.objects.create(
            seller=user, document_type="cni",
            document_front="kyc/sellers/1/f.jpg", document_back="kyc/sellers/1/b.jpg",
            status=SellerKYC.Status.VERIFIED, submitted_at=None,
        )

    def _create_store_via_api(self, owner, name):
        self._verify_kyc(owner)
        self.client.force_authenticate(owner)
        return self.client.post("/api/catalog/stores/", {"name": name}, format="json")

    def test_merchant_can_create_one_store(self):
        # Sans boutique : la création de sa première (et seule) boutique réussit.
        fresh = self._make_merchant("fresh@example.com")
        response = self._create_store_via_api(fresh, "Ma première boutique")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(fresh.stores.count(), 1)

    def test_merchant_cannot_create_a_second_store(self):
        # Règle « 1 vendeur = 1 boutique » (spec §1), appliquée côté backend :
        # un commerçant qui possède déjà une boutique n'en crée pas une seconde,
        # quel que soit le statut de la boutique existante.
        response = self._create_store_via_api(self.owner, "Deuxième boutique")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.owner.stores.count(), 1)

    def test_merchant_can_recreate_store_after_deleting_the_previous_one(self):
        # Supprimer sa boutique libère le droit d'en rouvrir une nouvelle.
        self.store.delete()
        response = self._create_store_via_api(self.owner, "Nouvelle boutique")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.owner.stores.count(), 1)

    def test_admin_can_create_a_store_for_a_seller(self):
        # L'admin reste libre (gestion manuelle d'un compte vendeur).
        admin = User.objects.create_user(username="admin@example.com", email="admin@example.com", password="testpass123", is_verified=True)
        UserRole.objects.create(user=admin, role=Role.objects.get_or_create(name=Role.RoleName.ADMIN)[0])
        self.store.delete()
        self.client.force_authenticate(admin)
        response = self.client.post(
            "/api/catalog/stores/",
            {"name": "Boutique gérée", "owner": str(self.owner.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_owner_can_upload_image(self):
        self.client.force_authenticate(self.owner)
        image = SimpleUploadedFile("photo.png", TINY_PNG, content_type="image/png")
        response = self.client.post(f"/api/catalog/products/{self.product.id}/images/", {"image": image}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.product.images.count(), 1)
        self.assertTrue(response.data["url"])

    def test_non_owner_cannot_upload_image(self):
        # Le produit est en statut "draft" : un autre commerçant ne le voit même
        # pas dans son queryset (404), ce qui est plus sûr qu'un 403 révélant
        # son existence.
        self.client.force_authenticate(self.other)
        image = SimpleUploadedFile("photo.png", TINY_PNG, content_type="image/png")
        response = self.client.post(f"/api/catalog/products/{self.product.id}/images/", {"image": image}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.product.images.count(), 0)

    def test_non_owner_cannot_upload_image_to_active_product(self):
        # Même un produit actif (donc visible publiquement) reste protégé en écriture.
        self.product.status = Product.Status.ACTIVE
        self.product.save()
        self.client.force_authenticate(self.other)
        image = SimpleUploadedFile("photo.png", TINY_PNG, content_type="image/png")
        response = self.client.post(f"/api/catalog/products/{self.product.id}/images/", {"image": image}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.product.images.count(), 0)

    def test_anyone_can_view_an_active_product_without_auth(self):
        # Régression : la vérification de propriété ne doit jamais bloquer la
        # simple lecture d'un produit, même pour un visiteur non connecté.
        self.product.status = Product.Status.ACTIVE
        self.product.save()
        response = self.client.get(f"/api/catalog/products/{self.product.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_another_authenticated_user_can_view_an_active_product(self):
        self.product.status = Product.Status.ACTIVE
        self.product.save()
        self.client.force_authenticate(self.other)
        response = self.client.get(f"/api/catalog/products/{self.product.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_owner_cannot_create_product_in_others_store(self):
        self.client.force_authenticate(self.other)
        response = self.client.post(
            "/api/catalog/products/",
            {"store": str(self.store.id), "name": "Intrus", "base_price": "500"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_variant_creation_creates_inventory_with_requested_quantity(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            "/api/catalog/variants/",
            {"product": str(self.product.id), "sku": "SKU-1", "price": "1000", "initial_quantity": 42},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        variant = ProductVariant.objects.get(sku="SKU-1")
        self.assertTrue(hasattr(variant, "inventory"))
        self.assertEqual(variant.inventory.quantity, 42)
        self.assertTrue(variant.is_available())

    def test_variant_without_sku_gets_auto_generated_unique_sku(self):
        """Le vendeur peut omettre la référence : un code unique est généré (pas d'erreur 400)."""
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            "/api/catalog/variants/",
            {"product": str(self.product.id), "price": "2000", "initial_quantity": 10},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        variant = ProductVariant.objects.get(product=self.product)
        self.assertTrue(variant.sku)
        self.assertTrue(variant.sku.startswith(f"P{self.product.id}-"))
        self.assertTrue(variant.is_available())
