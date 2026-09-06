import { create } from "zustand";
import * as shoppingApi from "@/api/shopping";

interface CartState {
  cartCount: number;
  fetchCart: () => void;
  addItem: (productVariant: string, quantity?: number) => Promise<void>;
  updateItem: (itemId: string, quantity: number) => Promise<void>;
  removeItem: (itemId: string) => Promise<void>;
  reset: () => void;
}

function computeCount(items: { quantity: number }[]) {
  return items.reduce((sum, i) => sum + i.quantity, 0);
}

export const useCartStore = create<CartState>()((set) => ({
  cartCount: 0,

  fetchCart: () => {
    shoppingApi
      .getCart()
      .then((cart) => set({ cartCount: computeCount(cart.items) }))
      .catch(() => set({ cartCount: 0 }));
  },

  addItem: async (productVariant, quantity = 1) => {
    const cart = await shoppingApi.addCartItem(productVariant, quantity);
    set({ cartCount: computeCount(cart.items) });
  },

  removeItem: async (itemId) => {
    const cart = await shoppingApi.removeCartItem(itemId);
    set({ cartCount: computeCount(cart.items) });
  },

  updateItem: async (itemId, quantity) => {
    const cart = await shoppingApi.updateCartItem(itemId, quantity);
    set({ cartCount: computeCount(cart.items) });
  },

  reset: () => set({ cartCount: 0 }),
}));
