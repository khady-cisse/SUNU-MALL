import { useState } from "react";
import { Link } from "react-router-dom";
import { BadgeCheck, Heart, ImageOff, Loader2, Plus } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { useCartStore } from "@/store/cartStore";
import { useWishlistStore } from "@/store/wishlistStore";
import type { Product } from "@/types";
import { formatPrice } from "@/lib/utils";

export function ProductCard({ product, sponsored }: { product: Product; sponsored?: boolean }) {
  const addCartItem = useCartStore((s) => s.addItem);
  const isFav = useWishlistStore((s) => s.has(product.id));
  const toggleFavorite = useWishlistStore((s) => s.toggleItem);
  const [adding, setAdding] = useState(false);
  const image = product.images[0]?.url;

  const variants = product.variants ?? [];
  const defaultVariant = variants[0];
  const prices = variants.map((v) => parseFloat(v.price)).filter((p) => !Number.isNaN(p));
  const minPrice = prices.length ? Math.min(...prices) : parseFloat(product.base_price) || 0;
  const priceLabel = variants.length > 1 ? `À partir de ${formatPrice(minPrice)}` : formatPrice(minPrice);
  const isAvailable = defaultVariant ? defaultVariant.is_available : false;

  async function addToCart() {
    if (!defaultVariant) return;
    setAdding(true);
    try {
      await addCartItem(defaultVariant.id, 1, {
        product_name: product.name,
        unit_price: defaultVariant.price,
        store: product.store,
      });
    } finally {
      setAdding(false);
    }
  }

  function handleAddToCart(e: React.MouseEvent) {
    e.preventDefault();
    addToCart();
  }

  async function handleToggleFavorite(e: React.MouseEvent) {
    e.preventDefault();
    try {
      await toggleFavorite(product.id, {
        product_name: product.name,
        product_price: String(minPrice),
      });
    } catch {
      // Ignorer : le store gère l'état de façon réactive.
    }
  }

  return (
    <Link
      to={`/product/${product.id}`}
      className="group relative flex cursor-pointer flex-col overflow-hidden rounded-xl border border-gray-100 bg-white transition-all duration-300 hover:border-orange/40 hover:shadow-lg"
    >
      <div className="relative aspect-square overflow-hidden bg-gray-50">
        {image ? (
          <img
            src={image}
            alt={product.name}
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-gray-100 to-gray-200">
            <ImageOff className="h-10 w-10 text-gray-300" />
          </div>
        )}

        {sponsored && (
          <Badge variant="sponsored" className="absolute left-2 top-2 z-10">
            Sponsorisé
          </Badge>
        )}

        {!isAvailable && defaultVariant && (
          <span className="absolute left-2 top-2 rounded-md bg-gray-700 px-2 py-0.5 text-[11px] font-bold text-white shadow">
            Rupture de stock
          </span>
        )}

        <button
          onClick={handleToggleFavorite}
          aria-label={isFav ? "Retirer des favoris" : "Ajouter aux favoris"}
          aria-pressed={isFav}
          className="absolute right-2 top-2 grid h-8 w-8 place-items-center rounded-full border border-gray-100 bg-white shadow transition-colors hover:border-orange"
        >
          <Heart className={isFav ? "h-4 w-4 fill-orange text-orange" : "h-4 w-4 text-gray-400"} />
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-1 p-3">
        <p className="flex items-center gap-1 truncate text-[11px] text-gray-400">
          <span className="truncate">{product.store_name}</span>
          {product.store_is_verified && (
            <BadgeCheck className="h-3 w-3 shrink-0 text-green-600" aria-label="Vendeur vérifié" />
          )}
        </p>
        <p className="line-clamp-2 min-h-[2.5em] text-sm font-semibold leading-snug text-gray-800">{product.name}</p>

        <div className="mt-auto flex items-center justify-between pt-1">
          <span className="text-base font-bold text-orange">{priceLabel}</span>
          <button
            onClick={handleAddToCart}
            disabled={!isAvailable || adding || !defaultVariant}
            className="grid h-8 w-8 place-items-center rounded-lg bg-orange text-white shadow transition-all duration-200 hover:scale-110 hover:bg-orange-dark active:scale-95 disabled:opacity-40 disabled:hover:scale-100"
          >
            {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </Link>
  );
}
