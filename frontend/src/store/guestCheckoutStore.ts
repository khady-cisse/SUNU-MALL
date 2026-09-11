import { create } from "zustand";

interface GuestCheckoutState {
  isOpen: boolean;
  pendingAction: (() => void | Promise<void>) | null;
  open: (action: () => void | Promise<void>) => void;
  close: () => void;
}

/**
 * Pilote le modal "achat sans compte" depuis n'importe quel point d'entrée
 * (ProductCard répété dans une grille, product-detail…) sans dupliquer le
 * modal à chaque endroit : un seul <GuestCheckoutModal /> monté une fois
 * lit cet état, et rejoue `pendingAction` une fois le compte invité créé.
 */
export const useGuestCheckoutStore = create<GuestCheckoutState>((set) => ({
  isOpen: false,
  pendingAction: null,
  open: (action) => set({ isOpen: true, pendingAction: action }),
  close: () => set({ isOpen: false, pendingAction: null }),
}));
