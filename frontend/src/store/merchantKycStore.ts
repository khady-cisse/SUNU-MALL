import { create } from "zustand";
import * as kycApi from "@/api/kyc";

/**
 * Statut KYC du vendeur connecté, partagé par le header public et l'écran de
 * blocage. Permet de « masquer » la session d'un commerçant dont l'identité
 * n'est pas encore approuvée sur les pages publiques : le compte existe mais
 * n'est jamais affiché comme connecté hors de son espace.
 *
 * Non persisté : l'état se recalcule après chaque connexion.
 */
interface MerchantKycState {
  /** Statut du dossier ("VERIFIED", "PENDING", "REJECTED"…) ou null (aucun dossier / pas encore consulté). */
  status: string | null;
  /** Vrai dès que getMySellerKyc a répondu au moins une fois pour cette session. */
  checked: boolean;
  checkOnce: () => void;
  reset: () => void;
}

export const useMerchantKycStore = create<MerchantKycState>((set, get) => ({
  status: null,
  checked: false,

  checkOnce: () => {
    if (get().checked) return;
    set({ checked: true });
    kycApi
      .getMySellerKyc()
      .then((kyc) => set({ status: kyc?.status ?? null }))
      .catch(() => set({ status: null }));
  },

  reset: () => set({ status: null, checked: false }),
}));

/** Vrai si l'utilisateur est un commerçant dont l'identité n'est pas encore approuvée. */
export function isPendingMerchant(status: string | null): boolean {
  return status !== null && status !== "VERIFIED";
}