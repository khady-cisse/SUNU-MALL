import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { Category, Paginated, Product, ProductImage, ProductVariant, Review, Store, StoreCategory, StoreCategoryCount } from "@/types";

export interface StoreSettings {
  id: string;
  store: string;
  business_hours: Record<string, unknown>;
  min_order_amount: string;
  created_at: string;
  updated_at: string;
}

export async function listStores(params?: { search?: string }) {
  const qs = params?.search ? `?search=${encodeURIComponent(params.search)}` : "";
  const data = await apiGet<Paginated<Store>>(`/catalog/stores/${qs}`);
  return data.results;
}

export function getStore(id: string) {
  return apiGet<Store>(`/catalog/stores/${id}/`);
}

/**
 * Boutiques de l'utilisateur connecté, filtrées côté serveur (?owner=id) —
 * contrairement à `listStores`, ne dépend pas de la 1ère page de la liste
 * globale (qui se tronque silencieusement à 20 boutiques une fois la
 * marketplace suffisamment grande).
 */
export async function listMyStores() {
  const userId = useAuthStore.getState().user?.id;
  if (!userId) return [];
  const data = await apiGet<Paginated<Store>>(`/catalog/stores/?owner=${userId}`);
  return data.results;
}

export function createStore(payload: {
  name: string;
  category?: number | null;
  phone?: string;
  description?: string;
  address?: string;
  city?: string;
}) {
  return apiPost<Store>("/catalog/stores/", payload);
}

/** Catégories de boutique (Électronique, Mode, ...) — pour le formulaire de création de boutique. */
export async function listStoreCategories() {
  return apiGet<StoreCategory[]>("/catalog/store-categories/");
}

export function approveStore(id: string) {
  return apiPost<Store>(`/catalog/stores/${id}/approve/`);
}

export function rejectStore(id: string, reason?: string) {
  return apiPost<Store>(`/catalog/stores/${id}/reject/`, { reason });
}

export function updateStorePosition(storeId: string, payload: { latitude: number; longitude: number }) {
  return apiPatch<Store>(`/catalog/stores/${storeId}/`, payload);
}

export function uploadStoreLogo(storeId: string, file: File) {
  const formData = new FormData();
  formData.append("logo", file);
  return apiPost<Store>(`/catalog/stores/${storeId}/logo/`, formData);
}

export function uploadStoreBanner(storeId: string, file: File) {
  const formData = new FormData();
  formData.append("banner", file);
  return apiPost<Store>(`/catalog/stores/${storeId}/banner/`, formData);
}

export function getStoreSettings(storeId: string) {
  return apiGet<StoreSettings>(`/catalog/stores/${storeId}/settings/`);
}

export function updateStoreSettings(storeId: string, payload: { business_hours?: Record<string, unknown>; min_order_amount?: number }) {
  return apiPatch<StoreSettings>(`/catalog/stores/${storeId}/settings/`, payload);
}

export async function listCategories() {
  const data = await apiGet<Paginated<Category>>("/catalog/categories/");
  return data.results;
}

export async function listProducts(params?: { search?: string; store?: string; category?: string }) {
  const search = new URLSearchParams();
  if (params?.search) search.set("search", params.search);
  if (params?.store) search.set("store", params.store);
  if (params?.category) search.set("category", params.category);
  const qs = search.toString();
  const data = await apiGet<Paginated<Product>>(`/catalog/products/${qs ? `?${qs}` : ""}`);
  return data.results;
}

/** Comme `listProducts({ store })`, mais parcourt toutes les pages — pour la gestion de catalogue d'un commerçant, qui doit voir la totalité de ses produits, pas seulement les 20 premiers. */
export async function listAllProductsForStore(storeId: string) {
  const all: Product[] = [];
  let page = 1;
  for (;;) {
    const data = await apiGet<Paginated<Product>>(`/catalog/products/?store=${storeId}&page=${page}`);
    all.push(...data.results);
    if (!data.next) break;
    page += 1;
  }
  return all;
}

/** Comme `listProducts`, mais renvoie l'enveloppe de pagination DRF complète (count/next/previous), pour les écrans de navigation catalogue avec pagination (recherche, catégories). */
export async function searchProducts(params?: {
  search?: string;
  store?: string;
  category?: string;
  page?: number;
  sponsored?: boolean;
}) {
  const qs = new URLSearchParams();
  if (params?.search) qs.set("search", params.search);
  if (params?.store) qs.set("store", params.store);
  if (params?.category) qs.set("category", params.category);
  if (params?.page) qs.set("page", String(params.page));
  if (params?.sponsored) qs.set("sponsored", "true");
  const query = qs.toString();
  return apiGet<Paginated<Product>>(`/catalog/products/${query ? `?${query}` : ""}`);
}

/** Comme `listStores`, mais renvoie l'enveloppe de pagination DRF complète, pour l'annuaire public des boutiques. */
export async function listStoresPaginated(params?: {
  search?: string;
  status?: string;
  page?: number;
  productCategory?: number | string;
  ordering?: string;
}) {
  const qs = new URLSearchParams();
  if (params?.search) qs.set("search", params.search);
  if (params?.status) qs.set("status", params.status);
  if (params?.page) qs.set("page", String(params.page));
  if (params?.productCategory) qs.set("product_category", String(params.productCategory));
  if (params?.ordering) qs.set("ordering", params.ordering);
  const query = qs.toString();
  return apiGet<Paginated<Store>>(`/catalog/stores/${query ? `?${query}` : ""}`);
}

/** Catégories produit réellement représentées par au moins une boutique active, avec leur nombre réel de boutiques — pour le filtre de /boutiques. */
export async function listStoreCategoryCounts() {
  return apiGet<StoreCategoryCount[]>("/catalog/categories/store-counts/");
}

export function getProduct(id: string) {
  return apiGet<Product>(`/catalog/products/${id}/`);
}

export function listSponsoredProducts() {
  return apiGet<Product[]>("/catalog/products/sponsored/");
}

export function listBestSellers(params?: { store?: string }) {
  const qs = params?.store ? `?store=${params.store}` : "";
  return apiGet<Product[]>(`/catalog/products/best_sellers/${qs}`);
}

/** Produits fréquemment achetés avec celui-ci (co-achat), à défaut d'autres produits de la même catégorie. */
export function listSimilarProducts(productId: string) {
  return apiGet<Product[]>(`/catalog/products/${productId}/similar/`);
}

export function createProduct(payload: {
  store: string;
  category?: string | null;
  brand?: string;
  name: string;
  description?: string;
  base_price: number;
  status?: "draft" | "active" | "inactive";
}) {
  return apiPost<Product>("/catalog/products/", payload);
}

export function updateProduct(id: string, payload: Partial<Product>) {
  return apiPatch<Product>(`/catalog/products/${id}/`, payload);
}

export function deleteProduct(id: string) {
  return apiDelete<void>(`/catalog/products/${id}/`);
}

export function createVariant(payload: {
  product: string;
  sku?: string;
  attributes?: Record<string, string>;
  price: number;
  initial_quantity?: number;
}) {
  return apiPost<ProductVariant>("/catalog/variants/", payload);
}

export function uploadProductImage(productId: string, file: File) {
  const formData = new FormData();
  formData.append("image", file);
  return apiPost<ProductImage>(`/catalog/products/${productId}/images/`, formData);
}

export function deleteProductImage(productId: string, imageId: string) {
  return apiDelete<void>(`/catalog/products/${productId}/images/?image_id=${imageId}`);
}

export async function listReviews(productId: string) {
  const data = await apiGet<Paginated<Review>>(`/catalog/reviews/?product=${productId}`);
  return data.results;
}

export function createReview(payload: { product: string; rating: number; comment?: string }) {
  return apiPost<Review>("/catalog/reviews/", payload);
}
