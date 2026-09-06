"""
Peuple la marketplace avec des données de démonstration : boutiques
approuvées (avec vendeurs KYC VERIFIED), produits avec images générées,
stocks, avis et quelques campagnes de sponsoring — sans réseau, les images
sont créées localement (Pillow) puis uploadées sur le stockage média.

Idempotent : relancer le script ajoute plus de boutiques/produits sans
dupliquer celles qui existent déjà (les noms de boutiques font office de
clé d'existence).

Usage :
    python manage.py seed_demo --stores 12 --products-per-store 6

Comptes créés (mot de passe commun : Demo@12345) :
    demo.vendeur{i}@sunumall.com   (vendeurs, KYC VERIFIED)
    demo.client{i}@sunumall.com    (clients ayant écrit des avis)
"""
import random
import uuid
from datetime import timedelta
from io import BytesIO
from pathlib import Path, PurePosixPath

from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.users.models import Role, User, UserRole

DEMO_PASSWORD = "Demo@12345"
DEMO_MERCHANT_PREFIX = "demo.vendeur"
DEMO_CLIENT_PREFIX = "demo.client"

# (Sénégal) noms de boutiques, villes et coordonnées (région de Dakar).
STORE_NAMES = [
    ("Keur Élégance", "Mode"),
    ("Techno Place", "Électronique"),
    ("Saveurs du Terroir", "Alimentation"),
    ("Bella Beauté", "Beauté & Bien-être"),
    ("Confort & Maison", "Maison & Électroménager"),
    ("Oxygène Sport", "Sport"),
    ("Boutique Thiossane", "Mode"),
    ("Dakar Digital", "Électronique"),
    ("Marché Bokk", "Alimentation"),
    ("Éclat Sen Équipement", "Maison & Électroménager"),
    ("Fit Dakar", "Sport"),
    ("Prestige Mode Afrique", "Mode"),
]
CITIES = ["Dakar", "Thiès", "Mbour", "Saint-Louis", "Touba", "Tivaouane"]

PRODUCTS_BY_CATEGORY = {
    "Électronique": [
        ("Smartphone PRIME X", 45000, 185000),
        ("Écouteurs sans fil AIRGO", 7500, 25000),
        ("Enceinte Bluetooth BOOM", 12500, 42000),
        ("Montre connectée FITWATCH", 18500, 65000),
        ("Chargeur rapide 65W", 5000, 15000),
        ("TV LED 43\" SMART", 140000, 320000),
    ],
    "Mode": [
        ("Boubou brodé homme", 25000, 90000),
        ("Robe en wax premium", 18000, 65000),
        ("Chemise pagne élégante", 12000, 35000),
        ("Sacs à main cuir", 15000, 45000),
        ("Chaussures habillées", 20000, 55000),
        ("Ensemble tailleur femme", 28000, 85000),
    ],
    "Alimentation": [
        ("Huile d'arachide pure 2L", 3500, 8000),
        ("Riz parfumé 5kg", 4500, 9500),
        ("Café du Sénégal 500g", 4000, 9000),
        ("Miel naturel 1kg", 8000, 15000),
        ("Thé Laya 1kg", 2000, 6000),
        ("Arachides grillées 1kg", 2500, 5500),
    ],
    "Beauté & Bien-être": [
        ("Savon noir artisanal", 1500, 4500),
        ("Huile de coco pure 1L", 6000, 12000),
        ("Karité brut 500g", 4000, 9000),
        ("Parfum oriental 100ml", 12000, 35000),
        ("Gommage corps shea", 3000, 8000),
        ("Sérum visage vitamine C", 9000, 22000),
    ],
    "Maison & Électroménager": [
        ("Machine à coudre portable", 95000, 185000),
        ("Robot mixeur 3 vitesses", 25000, 55000),
        ("Fer à repasser vapeur", 15000, 38000),
        ("Radiateur électrique", 20000, 48000),
        ("Ventilateur tour 30cm", 18000, 42000),
        ("Set de marmites inox", 12000, 38000),
    ],
    "Sport": [
        ("Ballon de foot taille 5", 8000, 25000),
        ("Chaussures de running", 18000, 60000),
        ("Maillot national domicile", 12000, 30000),
        ("Haltères 10kg (paire)", 15000, 40000),
        ("Tapis de yoga 6mm", 5000, 12000),
        ("Corde à sauter pro", 3000, 8000),
    ],
}

REVIEW_COMMENTS = [
    "Très satisfait de la qualité, livraison rapide.",
    "Correspond parfaitement à la description.",
    "Bon rapport qualité/prix, je recommande.",
    "Joli produit, emballage soigné.",
    "Livré en avance, excellent service.",
    "Conforme et fonctionnel, merci au vendeur.",
    "Je rachèterai, très bonne boutique.",
]

# Palette de fonds pour les images générées (dégradés agréables).
PALETTES = [
    ((232, 74, 95), (254, 206, 119)),
    ((46, 84, 153), (0, 210, 190)),
    ((140, 69, 190), (255, 168, 115)),
    ((29, 161, 90), (141, 232, 191)),
    ((216, 62, 42), (255, 196, 116)),
    ((38, 132, 188), (131, 225, 193)),
]


class Command(BaseCommand):
    help = "Peuple la marketplace avec boutiques, produits, images, stocks, avis et sponsoring de démo."

    def add_arguments(self, parser):
        parser.add_argument("--stores", type=int, default=12, help="Nombre de boutiques de démo à garantir (défaut 12).")
        parser.add_argument(
            "--products-per-store", type=int, default=6,
            help="Nombre de produits à garantir par boutiques (défaut 6).",
        )

    def handle(self, *args, **options):
        from apps.catalog.models import (
            Category, Inventory, Product, ProductImage, ProductVariant,
            Review, Store, StoreCategory, StoreSettings,
        )
        from apps.kyc.models import SellerKYC
        from apps.monetization.models import SponsoredProduct

        random.seed(2026)
        target_stores = options["stores"]
        products_per_store = options["products_per_store"]
        today = timezone.now().date()

        # --- Catégories de produits -------------------------------------------------
        category_by_name = {}
        store_categories = {sc.name: sc for sc in StoreCategory.objects.all()}
        for name in store_categories:
            cat, _ = Category.objects.get_or_create(name=name)
            category_by_name[name] = cat

        # --- Vendeurs + clients de démo ---------------------------------------------
        merchant_role = Role.objects.get(name=Role.RoleName.MERCHANT)
        client_role = Role.objects.get(name=Role.RoleName.CLIENT)

        def ensure_user(email, first_name, role, phone="+221 77 000 00 00"):
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "password": make_password(DEMO_PASSWORD),
                    "first_name": first_name,
                    "is_active": True,
                    "is_verified": True,
                    "phone": phone,
                },
            )
            UserRole.objects.get_or_create(user=user, role=role)
            return user, created

        merchants, clients = [], []
        for i in range(1, max(2, target_stores // 3) + 1):
            merchant, _ = ensure_user(
                f"{DEMO_MERCHANT_PREFIX}{i}@sunumall.com", f"Vendeur Démo {i}", merchant_role,
            )
            SellerKYC.objects.get_or_create(
                seller=merchant,
                defaults={
                    "document_type": "CNI",
                    "document_front": "",
                    "document_back": "",
                    "status": SellerKYC.Status.VERIFIED,
                    "submitted_at": timezone.now() - timedelta(days=7),
                    "verified_at": timezone.now() - timedelta(days=6),
                },
            )
            merchants.append(merchant)
        for i in range(1, 4):
            client, _ = ensure_user(f"{DEMO_CLIENT_PREFIX}{i}@sunumall.com", f"Client Démo {i}", client_role)
            clients.append(client)

        created_stores = 0
        created_products = 0
        created_sponsorships = 0
        created_reviews = 0

        for idx, (store_name, category_name) in enumerate(STORE_NAMES):
            if idx >= target_stores:
                break
            store, was_created = Store.objects.get_or_create(
                name=store_name,
                defaults={
                    "owner": merchants[idx % len(merchants)],
                    "category": store_categories.get(category_name),
                    "description": (
                        f"{store_name} — boutique sénégalaise {category_name.lower()}, "
                        "produits vérifiés, livraison rapide à Dakar et alentours."
                    ),
                    "phone": f"+221 77 {random.randint(100, 999)} {random.randint(10, 99)} {random.randint(10, 99)}",
                    "address": f"Avenue {random.choice(['Cheikh Anta Diop', 'Seydou Nourou Tall', 'Bourguiba', 'Pompidou'])}",
                    "city": random.choice(CITIES),
                    "status": Store.Status.ACTIVE,
                    "latitude": round(random.uniform(14.68, 14.76), 6),
                    "longitude": round(random.uniform(-17.47, -17.38), 6),
                },
            )
            StoreSettings.objects.get_or_create(store=store)
            store_cat_name = store.category.name if store.category else list(category_by_name)[idx % len(category_by_name)]
            templates = PRODUCTS_BY_CATEGORY.get(store_cat_name) or PRODUCTS_BY_CATEGORY["Mode"]
            if was_created:
                created_stores += 1

            existing_products = store.products.count()
            products_to_create = max(0, products_per_store - existing_products)
            for _ in range(products_to_create):
                if not templates:
                    break
                name, low, high = random.choice(templates)
                # Éviter le doublon exact dans la même boutique.
                if store.products.filter(name=name).exists():
                    continue
                base_price = random.randint(low, high)
                product = Product.objects.create(
                    store=store,
                    category=category_by_name.get(store_cat_name),
                    name=name,
                    description=(
                        f"{name}. Article proposé par {store_name} — "
                        "qualité contrôlée et livraison sur tout le Sénégal."
                    ),
                    base_price=base_price,
                    status=Product.Status.ACTIVE,
                )
                variant = ProductVariant.objects.create(
                    product=product,
                    sku=f"P{product.id}-{uuid.uuid4().hex[:6].upper()}",
                    price=base_price,
                )
                Inventory.objects.create(
                    variant=variant,
                    quantity=random.randint(15, 120),
                )
                image_file = self._generate_image(name)
                ProductImage.objects.create(
                    product=product,
                    image=ContentFile(image_file.read(), name=f"products/{product.id}.png"),
                    position=0,
                )
                created_products += 1

                # Sponsoring : 1 produit sur 2 est mis en avant (carrousel "Sponsorisé").
                if created_products % 2 == 0:
                    SponsoredProduct.objects.get_or_create(
                        product=product,
                        defaults={
                            "daily_budget": random.randint(2000, 8000),
                            "starts_at": today - timedelta(days=5),
                            "ends_at": today + timedelta(days=20),
                            "status": SponsoredProduct.Status.ACTIVE,
                        },
                    )
                    created_sponsorships += 1

                # Avis de clients de démo (2 à 3 par produit).
                reviewed = set()
                for client in random.sample(clients, k=random.randint(2, 3)):
                    if client.id in reviewed:
                        continue
                    reviewed.add(client.id)
                    _, review_created = Review.objects.get_or_create(
                        product=product,
                        user=client,
                        defaults={
                            "rating": random.choices([3, 4, 5], weights=[1, 4, 5])[0],
                            "comment": random.choice(REVIEW_COMMENTS),
                        },
                    )
                    if review_created:
                        created_reviews += 1

        total = {
            "boutiques": Store.objects.count(),
            "produits": Product.objects.count(),
            "images": ProductImage.objects.count(),
            "avis": Review.objects.count(),
            "sponsorisés": SponsoredProduct.objects.filter(status=SponsoredProduct.Status.ACTIVE).count(),
            "stocks": Inventory.objects.count(),
        }
        self.stdout.write(self.style.SUCCESS(
            f"Seed terminé. Total marketplace : {total}.\n"
            f"  Créé ce coup-ci : {created_stores} boutiques, {created_products} produits, "
            f"{created_reviews} avis.\n"
            f"  Vendeurs : {len(merchants)} (KYC VERIFIED), clients : {len(clients)}.\n"
            f"  Mot de passe commun des comptes démo : {DEMO_PASSWORD}"
        ))

    def _generate_image(self, name):
        """PNG 600x600 : dégradé coloré + initiales du produit (aucun réseau requis)."""
        from PIL import Image, ImageDraw

        top, bottom = random.choice(PALETTES)
        size = 600
        img = Image.new("RGB", (size, size))
        px = img.load()
        for y in range(size):
            t = y / size
            r = round(top[0] + (bottom[0] - top[0]) * t)
            g = round(top[1] + (bottom[1] - top[1]) * t)
            b = round(top[2] + (bottom[2] - top[2]) * t)
            for x in range(size):
                px[x, y] = (r, g, b)
        draw = ImageDraw.Draw(img)
        initials = "".join(w[0] for w in name.split()[:2] if w[0].isascii() and w[0].isalpha()).upper()[:3] or "SM"
        try:
            bbox = draw.textbbox((0, 0), initials)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            draw.text(((size - w) / 2, (size - h) / 2), initials, fill=(255, 255, 255))
        except Exception:
            pass
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf