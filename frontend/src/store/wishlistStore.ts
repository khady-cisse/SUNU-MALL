import { create } from "zustand";
import * as shoppingApi from "@/api/shopping";

interface WishlistState {
  wishlistCount: number;
  /** Ensemble des IDs de produits déjà en favoris. */
  productIds: Set<string>;
  /** Initialise l'état (favoris du user connecté). */
  fetchWishlist: () => void;
  /** Bascule l'état favori d'un produit. Retourne true si ajouté, false si retiré. */
  toggleItem: (productId: string) => Promise<boolean>;
  /** Indique si un produit est actuellement en favoris. */
  has: (productId: string) => boolean;
  reset: () => void;
}

function toProductIds(wishlist: { items: { product: string }[] }) {
  return new Set(wishlist.items.map((i) => i.product));
}

export const useWishlistStore = create<WishlistState>()((set, get) => ({
  wishlistCount: 0,
  productIds: new Set<string>(),

  fetchWishlist: () => {
    shoppingApi
      .getWishlist()
      .then((wishlist) => set({ wishlistCount: wishlist.items.length, productIds: toProductIds(wishlist) }))
      .catch(() => set({ wishlistCount: 0, productIds: new Set() }));
  },

  toggleItem: async (productId) => {
    if (get().has(productId)) {
      const wishlist = await shoppingApi.removeWishlistItem(productId);
      set({ wishlistCount: wishlist.items.length, productIds: toProductIds(wishlist) });
      return false;
    }
    const wishlist = await shoppingApi.addWishlistItem(productId);
    set({ wishlistCount: wishlist.items.length, productIds: toProductIds(wishlist) });
    return true;
  },

  has: (productId) => get().productIds.has(productId),

  reset: () => set({ wishlistCount: 0, productIds: new Set() }),
}));
