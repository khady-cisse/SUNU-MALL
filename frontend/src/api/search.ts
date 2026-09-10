import { apiGet, apiPost } from "@/lib/api";

export interface SearchResultItem {
  type: string;
  label: string;
  subtitle?: string;
  meta?: { status?: string; method?: string };
  to: string;
}

export interface AdvancedSearchFilters {
  q?: string;
  entities?: string[];
  status?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
}

export async function globalSearch(query: string) {
  return apiGet<Record<string, SearchResultItem[]>>(`/search/?q=${encodeURIComponent(query)}`);
}

export async function advancedSearch(filters: AdvancedSearchFilters) {
  return apiPost<Record<string, SearchResultItem[]>>("/search/advanced/", {
    query: filters.q ?? "",
    entities: filters.entities ?? [],
    status: filters.status ?? "",
    date_from: filters.date_from ?? "",
    date_to: filters.date_to ?? "",
    limit: filters.limit ?? 20,
  });
}