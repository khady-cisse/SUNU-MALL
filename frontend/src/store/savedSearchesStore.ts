import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AdvancedSearchFilters } from "@/api/search";

interface SavedSearch {
  id: string;
  name: string;
  filters: AdvancedSearchFilters;
  createdAt: string;
}

interface SavedSearchesState {
  saved: SavedSearch[];
  addSearch: (name: string, filters: AdvancedSearchFilters) => void;
  removeSearch: (id: string) => void;
}

export const useSavedSearchesStore = create<SavedSearchesState>()(
  persist(
    (set) => ({
      saved: [],
      addSearch: (name, filters) =>
        set((state) => ({
          saved: [
            {
              id: crypto.randomUUID(),
              name,
              filters,
              createdAt: new Date().toISOString(),
            },
            ...state.saved,
          ].slice(0, 20),
        })),
      removeSearch: (id) =>
        set((state) => ({ saved: state.saved.filter((s) => s.id !== id) })),
    }),
    { name: "sunu-mall-admin-saved-searches" },
  ),
);