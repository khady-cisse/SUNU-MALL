import { create } from "zustand";
import type { Address, CartItem } from "@/types";

interface CheckoutState {
  /** Boutique unique (commande classique) ou `null` pour un panier
   * multi-boutiques (les boutiques sont déduites des articles côté serveur). */
  storeId: string | null;
  storeName: string | null;
  items: CartItem[];
  address: Address | null;
  deliveryMethod: "standard" | "express" | "pickup";
  deliveryFee: number;
  paymentMethod: "wave" | "orange_money" | "card";
  startCheckout: (storeId: string | null, storeName: string | null, items: CartItem[]) => void;
  setAddress: (address: Address) => void;
  setDelivery: (method: "standard" | "express" | "pickup", fee: number) => void;
  setPaymentMethod: (method: "wave" | "orange_money" | "card") => void;
  reset: () => void;
}

export const useCheckoutStore = create<CheckoutState>()((set) => ({
  storeId: null,
  storeName: null,
  items: [],
  address: null,
  deliveryMethod: "standard",
  deliveryFee: 0,
  paymentMethod: "wave",

  startCheckout: (storeId, storeName, items) => set({ storeId, storeName, items }),
  setAddress: (address) => set({ address }),
  setDelivery: (deliveryMethod, deliveryFee) => set({ deliveryMethod, deliveryFee }),
  setPaymentMethod: (paymentMethod) => set({ paymentMethod }),
  reset: () =>
    set({
      storeId: null,
      storeName: null,
      items: [],
      address: null,
      deliveryMethod: "standard",
      deliveryFee: 0,
      paymentMethod: "wave",
    }),
}));
