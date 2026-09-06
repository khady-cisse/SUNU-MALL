import { create } from "zustand";
import type { AuthUser, Role } from "@/types";

// La session n'est plus persistée (localStorage) : la plateforme s'ouvre
// toujours « Se connecter ». On nettoie l'ancienne clé si elle existait.
if (typeof localStorage !== "undefined") {
  localStorage.removeItem("sunu-mall-auth");
}

export type { AuthUser, Role };

export interface LoginPayload {
  user: AuthUser;
  access: string | null;
  refresh: string | null;
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  hasHydrated: boolean;
  loginSuccess: (payload: LoginPayload) => void;
  setTokens: (access: string, refresh?: string) => void;
  updateUser: (patch: Partial<AuthUser>) => void;
  logout: () => void;
  hasRole: (role: Role) => boolean;
  setHasHydrated: (value: boolean) => void;
}

export const useAuthStore = create<AuthState>()((set, get) => ({
  user: null,
  accessToken: null,
  refreshToken: null,
  hasHydrated: true,

  loginSuccess: ({ user, access, refresh }) =>
    set({ user, accessToken: access, refreshToken: refresh }),

  setTokens: (access, refresh) =>
    set((state) => ({
      accessToken: access,
      refreshToken: refresh ?? state.refreshToken,
    })),

  updateUser: (patch) => set((state) => (state.user ? { user: { ...state.user, ...patch } } : {})),

  logout: () => set({ user: null, accessToken: null, refreshToken: null }),

  hasRole: (role) => !!get().user?.roles.includes(role),

  setHasHydrated: (value) => set({ hasHydrated: value }),
}));
