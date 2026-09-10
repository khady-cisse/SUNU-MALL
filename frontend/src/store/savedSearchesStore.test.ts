import { beforeEach, describe, expect, it } from "vitest";
import { useSavedSearchesStore } from "./savedSearchesStore";
import type { AdvancedSearchFilters } from "@/api/search";

const filters: AdvancedSearchFilters = {
  q: "palme",
  entities: ["products", "stores"],
  status: "active",
  date_from: "2026-01-01",
  date_to: "2026-12-31",
  limit: 20,
};

describe("useSavedSearchesStore", () => {
  beforeEach(() => {
    useSavedSearchesStore.setState({ saved: [] });
  });

  it("starts with no saved searches", () => {
    expect(useSavedSearchesStore.getState().saved).toEqual([]);
  });

  it("addSearch prepends the search with name and filters", () => {
    useSavedSearchesStore.getState().addSearch("Produits palme", filters);
    const { saved } = useSavedSearchesStore.getState();
    expect(saved).toHaveLength(1);
    expect(saved[0].name).toBe("Produits palme");
    expect(saved[0].filters).toEqual(filters);
    expect(saved[0].id).toBeTruthy();
    expect(saved[0].createdAt).toBeTruthy();
  });

  it("keeps the most recent search on top", () => {
    const store = useSavedSearchesStore.getState();
    store.addSearch("Recherche A", { q: "a" });
    store.addSearch("Recherche B", { q: "b" });
    const { saved } = useSavedSearchesStore.getState();
    expect(saved.map((s) => s.name)).toEqual(["Recherche B", "Recherche A"]);
  });

  it("caps the list at 20 searches", () => {
    const store = useSavedSearchesStore.getState();
    for (let i = 0; i < 25; i++) {
      store.addSearch(`S ${i}`, { q: `q${i}` });
    }
    const { saved } = useSavedSearchesStore.getState();
    expect(saved).toHaveLength(20);
    expect(saved[0].name).toBe("S 24");
  });

  it("removeSearch removes only the matching id", () => {
    const store = useSavedSearchesStore.getState();
    store.addSearch("Garder", { q: "keep" });
    store.addSearch("Supprimer", { q: "drop" });
    const { saved } = useSavedSearchesStore.getState();
    const toRemove = saved.find((s) => s.name === "Supprimer")!;
    useSavedSearchesStore.getState().removeSearch(toRemove.id);
    const remaining = useSavedSearchesStore.getState().saved;
    expect(remaining).toHaveLength(1);
    expect(remaining[0].name).toBe("Garder");
  });
});