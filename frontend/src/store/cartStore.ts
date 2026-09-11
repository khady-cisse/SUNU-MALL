import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Cart } from "@/types";
import * as shoppingApi from "@/api/shopping";
import { useAuthStore } from "@/store/authStore";

export interface GuestCartLine {
  id: string;
  product_variant: string;
  product_name: string;
  unit_price: string;
  quantity: number;
  store: string;
}

function computeCount(items: { quantity: number }[]) {
  return items.reduce((sum, i) => sum + i.quantity, 0);
}

interface CartState {
  cart: Cart | null;
  /** Articles locaux d'un visiteur non connecté (persistés en localStorage). */
  guestItems: GuestCartLine[];
  cartCount: number;
  loading: boolean;
  fetchCart: (opts?: { silent?: boolean }) => Promise<void>;
  addItem: (
    productVariant: string,
    quantity?: number,
    meta?: { product_name?: string; unit_price?: string; store?: string },
  ) => Promise<void>;
  updateItem: (itemId: string, quantity: number) => Promise<void>;
  removeItem: (itemId: string) => Promise<void>;
  clear: () => Promise<void>;
  reset: () => void;
  /** Pousse le panier local (invité) vers le serveur une fois le compte créé. */
  syncGuestToServer: () => Promise<void>;
}

const authed = () => !!useAuthStore.getState().accessToken;

export const useCartStore = create<CartState>()(
  persist(
    (set, get) => ({
      cart: null,
      guestItems: [],
      cartCount: 0,
      loading: false,

      async fetchCart({ silent } = {}) {
        if (!authed()) {
          set({ cart: null, cartCount: computeCount(get().guestItems), loading: false });
          return;
        }
        if (!silent) set({ loading: true });
        try {
          const cart = await shoppingApi.getCart();
          set({ cart, cartCount: computeCount(cart.items), loading: false });
        } catch {
          set({ cart: null, cartCount: computeCount(get().guestItems), loading: false });
        }
      },

      async addItem(productVariant, quantity = 1, meta) {
        if (!authed()) {
          const items = [...get().guestItems];
          const existing = items.find((i) => i.product_variant === productVariant);
          if (existing) {
            existing.quantity += quantity;
          } else {
            items.push({
              id: `local-${productVariant}`,
              product_variant: productVariant,
              product_name: meta?.product_name ?? "Produit",
              unit_price: meta?.unit_price ?? "0",
              quantity,
              store: meta?.store ?? "",
            });
          }
          set({ guestItems: items, cartCount: computeCount(items) });
          return;
        }
        const cart = await shoppingApi.addCartItem(productVariant, quantity);
        set({ cart, cartCount: computeCount(cart.items) });
      },

      async updateItem(itemId, quantity) {
        if (!authed()) {
          const items = get().guestItems.map((i) => (i.id === itemId ? { ...i, quantity } : i));
          set({ guestItems: items, cartCount: computeCount(items) });
          return;
        }
        const cart = await shoppingApi.updateCartItem(itemId, quantity);
        set({ cart, cartCount: computeCount(cart.items) });
      },

      async removeItem(itemId) {
        if (!authed()) {
          const items = get().guestItems.filter((i) => i.id !== itemId);
          set({ guestItems: items, cartCount: computeCount(items) });
          return;
        }
        const cart = await shoppingApi.removeCartItem(itemId);
        set({ cart, cartCount: computeCount(cart.items) });
      },

      async clear() {
        if (!authed()) {
          set({ guestItems: [], cartCount: 0 });
          return;
        }
        await shoppingApi.clearCart();
        set({ cart: null, cartCount: computeCount(get().guestItems) });
      },

      reset: () => set({ cart: null, cartCount: 0 }),

      async syncGuestToServer() {
        const guestItems = get().guestItems;
        if (!guestItems.length || !authed()) return;
        for (const item of guestItems) {
          try {
            await shoppingApi.addCartItem(item.product_variant, item.quantity);
          } catch {
            // On ignore les références devenues invalides ; les autres sont poussées.
          }
        }
        set({ guestItems: [], cartCount: 0 });
        await get().fetchCart({ silent: true });
      },
    }),
    {
      name: "sunu-mall-guest-cart",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ guestItems: s.guestItems }),
    },
  ),
);