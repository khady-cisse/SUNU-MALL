"""
Régénère les images de tous les produits et les uploade sur le stockage
média (MinIO) afin que chaque produit affiche une photo exploitable.

Sans réseau : les visuels sont créés localement (Pillow) — dégradé coloré
choisi selon la catégorie + nom du produit — puis sauvegardés dans le champ
ImageField existant (le stockage S3 s'en charge).

Usage :
    python manage.py fix_product_images
    python manage.py fix_product_images --force   # ré-upload même si un fichier existe
"""
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFont

from apps.catalog.models import Product, ProductImage

FONT_DIR = Path(__file__).resolve().parent.parent.parent / "fonts"

# Dégradés par catégorie (cohérents avec PRODUCTS_BY_CATEGORY du seed).
CATEGORY_PALETTES = {
    "Électronique": ((24, 40, 90), (52, 120, 200)),
    "Mode": ((90, 20, 120), (230, 120, 160)),
    "Alimentation": ((150, 80, 20), (240, 180, 80)),
    "Beauté & Bien-être": ((140, 40, 90), (245, 160, 190)),
    "Maison & Électroménager": ((20, 90, 90), (80, 200, 190)),
    "Sport": ((20, 100, 60), (120, 220, 140)),
}
FALLBACK_PALETTE = ((30, 30, 60), (120, 130, 180))


def _make_image(product):
    top, bottom = CATEGORY_PALETTES.get(
        product.category.name if product.category else "", FALLBACK_PALETTE
    )
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
    font_path = FONT_DIR / "arialbd.ttf"
    name = product.name or "Produit"

    def _usable_font(size_px):
        try:
            return ImageFont.truetype(str(font_path), size_px)
        except Exception:
            return ImageFont.load_default()

    def _wrap(text, font, max_width):
        """Coupe le texte sur plusieurs lignes pour tenir dans la carte."""
        words = text.split()
        lines = []
        current = ""
        for word in words:
            trial = (current + " " + word).strip()
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines[:3]

    title_font = _usable_font(44)
    lines = _wrap(name, title_font, size - 120)
    line_height = 56
    total = len(lines) * line_height
    y = (size - total) / 2
    for line in lines:
        w = draw.textlength(line, font=title_font)
        draw.text(((size - w) / 2, y), line, fill=(255, 255, 255), font=title_font)
        y += line_height

    draw.rounded_rectangle(
        (size - 96, size - 96, size - 24, size - 24),
        radius=36,
        fill=(255, 255, 255),
        outline=None,
    )
    draw.text(
        ((size - 60), (size - 60)),
        "S",
        fill=(top[0], top[1], top[2]),
        font=_usable_font(24),
    )

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _source_name(product, image):
    if image and image.pk:
        return f"products/{image.pk}.png"
    return f"products/{product.id}.png"


class Command(BaseCommand):
    help = "Régénère et uploade une photo pour chaque produit."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Ré-upload même si le fichier existe déjà.")

    def handle(self, *args, **options):
        force = options["force"]
        products = Product.objects.prefetch_related("images", "category").order_by("created_at")
        updated = created = skipped = failed = 0

        for product in products:
            try:
                product_image = product.images.filter(position=0).first()
                if not product_image:
                    product_image = product.images.first()
                if not product_image:
                    product_image = ProductImage.objects.create(product=product, position=0)

                if product_image.image and not force:
                    self.stdout.write(f"  - {product.name}: déjà une image, ignoré (--force pour forcer)")
                    skipped += 1
                    continue

                image_file = _make_image(product)
                product_image.image.save(
                    _source_name(product, product_image),
                    ContentFile(image_file.read()),
                    save=True,
                )
                created += 1
                self.stdout.write(f"  + {product.name}: image régénérée")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"  ! {product.name}: {exc}")
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Terminé : {created} images écrites, {skipped} ignorées, {updated} mises à jour, "
                f"{failed} échecs (total {products.count()} produits)."
            )
        )