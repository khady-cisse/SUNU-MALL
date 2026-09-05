"""
Listes de souhaits et paniers.
"""
import uuid
from django.db import models
from django.utils import timezone
from apps.users.models import User
from apps.catalog.models import Product, ProductVariant


class Wishlist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wishlist')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def add_product(self, product):
        WishlistItem.objects.get_or_create(wishlist=self, product=product)

    def remove_product(self, product):
        WishlistItem.objects.filter(wishlist=self, product=product).delete()

    def __str__(self):
        return f"Wishlist for {self.user.email}"


class WishlistItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='wishlist_items')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['wishlist', 'product']
        ordering = ['-added_at']

    def __str__(self):
        return f"{self.product.name} in wishlist"


class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def total_price(self):
        return sum(item.subtotal() for item in self.items.all())

    def add_item(self, variant, qty=1):
        inventory = getattr(variant, "inventory", None)
        if inventory is not None and inventory.available() < qty:
            raise ValueError(f"Stock insuffisant pour « {variant.product.name} » (disponible : {inventory.available()}).")
        item, created = CartItem.objects.get_or_create(cart=self, product_variant=variant)
        new_quantity = (item.quantity + qty) if not created else qty
        if inventory is not None and inventory.available() < new_quantity:
            raise ValueError(f"Stock insuffisant pour « {variant.product.name} » (disponible : {inventory.available()}).")
        item.quantity = new_quantity
        item.save()

    def clear(self):
        self.items.all().delete()

    def __str__(self):
        return f"Cart for {self.user.email}"


class CartItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='cart_items')
    quantity = models.IntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['cart', 'product_variant']
        ordering = ['-added_at']

    def subtotal(self):
        return self.quantity * self.product_variant.price

    def __str__(self):
        return f"{self.quantity} x {self.product_variant.product.name}"
