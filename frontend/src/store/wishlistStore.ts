import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Wishlist } from "@/types";
import * as shoppingApi from "@/api/shopping";
import { useAuthStore } from "@/store/authStore";

export interface GuestWishItem {
  id: string;
  product: string;
  product_name: string;
  product_price: string;
}

function toProductIds(wishlist: { items: { product: string }[] }) {
  return new Set(wishlist.items.map((i) => i.product));
}

interface WishlistState {
  wishlist: Wishlist | null;
  /** IDs des favoris du user connecté. */
  productIds: Set<string>;
  /** Favoris locaux d'un visiteur non connecté (persistés en localStorage). */
  guestItems: GuestWishItem[];
  wishlistCount: number;
  fetchWishlist: () => Promise<void>;
  /** Bascule l'état favori. Retourne true si ajouté, false si retiré. */
  toggleItem: (
    productId: string,
    meta?: { product_name?: string; product_price?: string },
  ) => Promise<boolean>;
  has: (productId: string) => boolean;
  reset: () => void;
  /** Pousse les favoris locaux (invité) vers le serveur une fois le compte créé. */
  syncGuestToServer: () => Promise<void>;
}

const authed = () => !!useAuthStore.getState().accessToken;

export const useWishlistStore = create<WishlistState>()(
  persist(
    (set, get) => ({
      wishlist: null,
      productIds: new Set<string>(),
      guestItems: [],
      wishlistCount: 0,

      async fetchWishlist() {
        if (!authed()) {
          set({ wishlist: null, wishlistCount: get().guestItems.length });
          return;
        }
        try {
          const wishlist = await shoppingApi.getWishlist();
          set({ wishlist, productIds: toProductIds(wishlist), wishlistCount: wishlist.items.length });
        } catch {
          set({ wishlist: null, wishlistCount: get().guestItems.length });
        }
      },

      async toggleItem(productId, meta) {
        if (!authed()) {
          const exists = get().guestItems.some((i) => i.product === productId);
          const items = exists
            ? get().guestItems.filter((i) => i.product !== productId)
            : [
                ...get().guestItems,
                {
                  id: `local-${productId}`,
                  product: productId,
                  product_name: meta?.product_name ?? "Produit",
                  product_price: meta?.product_price ?? "0",
                },
              ];
          set({ guestItems: items, wishlistCount: items.length });
          return !exists;
        }
        const exists = get().productIds.has(productId);
        const wishlist = exists
          ? await shoppingApi.removeWishlistItem(productId)
          : await shoppingApi.addWishlistItem(productId);
        set({ wishlist, productIds: toProductIds(wishlist), wishlistCount: wishlist.items.length });
        return !exists;
      },

      has: (productId) =>
        authed() ? get().productIds.has(productId) : get().guestItems.some((i) => i.product === productId),

      reset: () => set({ wishlist: null, productIds: new Set(), wishlistCount: 0 }),

      async syncGuestToServer() {
        const items = get().guestItems;
        if (!items.length || !authed()) return;
        for (const item of items) {
          try {
            await shoppingApi.addWishlistItem(item.product);
          } catch {
            // Ignoré : doublon ou produit indisponible.
          }
        }
        set({ guestItems: [], wishlistCount: 0 });
        await get().fetchWishlist();
      },
    }),
    {
      name: "sunu-mall-guest-wishlist",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ guestItems: s.guestItems }),
    },
  ),
);