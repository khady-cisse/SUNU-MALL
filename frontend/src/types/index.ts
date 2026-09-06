export type Role = "admin" | "merchant" | "client" | "driver";

/** Forme de réponse standard de la pagination DRF (PageNumberPagination) sur les endpoints `list`. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface AuthUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  roles: Role[];
  is_verified: boolean;
  /** false pour un compte invité (créé via guest-checkout, sans mot de passe défini). */
  has_password: boolean;
  /** true pour un compte créé par un admin (livreur) : mot de passe initial à changer. */
  must_change_password?: boolean;
}

export interface Category {
  id: string;
  parent: string | null;
  name: string;
  image_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface StoreCategory {
  id: number;
  name: string;
}

export interface Store {
  id: string;
  owner: string;
  owner_email: string;
  category: number | null;
  category_detail: StoreCategory | null;
  name: string;
  phone: string;
  description: string;
  address: string;
  city: string;
  /** Raison du dernier rejet — vide si jamais rejetée ou déjà approuvée. */
  rejection_reason: string;
  logo_url: string | null;
  banner_url: string | null;
  status: "inactive" | "active" | "suspended";
  latitude: string | null;
  longitude: string | null;
  /** Moyenne réelle des avis produits de la boutique — null si aucun avis. */
  rating: number | null;
  review_count: number;
  /** Catégories produit réellement vendues (dérivé des produits actifs). */
  category_names: string[];
  created_at: string;
  updated_at: string;
}

export interface StoreCategoryCount {
  id: number;
  name: string;
  store_count: number;
}

export interface ProductImage {
  id: string;
  url: string | null;
  position: number;
  created_at: string;
}

export interface ProductVariant {
  id: string;
  product: string;
  sku: string;
  attributes: Record<string, string>;
  price: string;
  is_available: boolean;
  quantity: number;
  created_at: string;
  updated_at: string;
}

export interface Product {
  id: string;
  store: string;
  store_name: string;
  category: string | null;
  brand: string;
  name: string;
  description: string;
  base_price: string;
  status: "draft" | "active" | "inactive";
  images: ProductImage[];
  variants: ProductVariant[];
  created_at: string;
  updated_at: string;
  /** Présent uniquement sur la réponse de `best_sellers` : quantité totale vendue. */
  sold_quantity?: number;
}

export interface Review {
  id: string;
  product: string;
  user: string;
  user_name: string;
  rating: number;
  comment: string;
  created_at: string;
}

export interface Address {
  id: string;
  user: string;
  label: string;
  street: string;
  city: string;
  country: string;
  latitude: string | null;
  longitude: string | null;
  created_at: string;
}

export interface CartItem {
  id: string;
  product_variant: string;
  product_name: string;
  unit_price: string;
  quantity: number;
  subtotal: number;
  added_at: string;
  store: string;
}

export interface Cart {
  id: string;
  user: string;
  items: CartItem[];
  total_price: number;
  created_at: string;
  updated_at: string;
}

export interface WishlistItem {
  id: string;
  product: string;
  product_name: string;
  product_price: string;
  added_at: string;
}

export interface Wishlist {
  id: string;
  user: string;
  items: WishlistItem[];
  created_at: string;
  updated_at: string;
}

export type DriverAvailability = "available" | "busy" | "offline";

export interface Driver {
  id: string;
  user: string;
  full_name: string;
  phone: string;
  email?: string;
  zone: number | null;
  vehicle_type: string;
  availability_status: DriverAvailability;
  last_position: { latitude: string; longitude: string } | null;
  position_updated_at: string | null;
  distance_km: number | null;
  created_at: string;
  updated_at: string;
}

export type DeliveryStatus = "pending" | "assigned" | "picked_up" | "delivered" | "cancelled";

export interface DeliveryTrackingPoint {
  latitude: string;
  longitude: string;
  recorded_at: string;
}

export interface Delivery {
  id: string;
  order: string;
  driver: string | null;
  driver_detail: Driver | null;
  status: DeliveryStatus;
  picked_up_at: string | null;
  delivered_at: string | null;
  last_position: DeliveryTrackingPoint | null;
  eta_seconds: number | null;
  created_at: string;
  updated_at: string;
}

/**
 * Événement poussé par le flux SSE de livraison (`/orders/deliveries/{id}/events/`).
 * `event` vaut "snapshot" (instantané de connexion), "position" (GPS), "status"
 * ou "assigned". Chaque événement porte l'état complet courant de la livraison.
 */
export interface DeliveryEvent {
  event: "snapshot" | "position" | "status" | "assigned";
  delivery_id?: string;
  status: DeliveryStatus;
  picked_up_at: string | null;
  delivered_at: string | null;
  eta_seconds: number | null;
  last_position: DeliveryTrackingPoint | null;
  message: string;
}

export interface OrderItem {
  id: string;
  product_variant: string;
  product_name: string;
  quantity: number;
  unit_price: string;
}

export type OrderStatus = "pending" | "paid" | "processing" | "shipped" | "delivered" | "cancelled";

export interface Order {
  id: string;
  customer: string;
  customer_name: string;
  customer_email: string;
  store: string;
  store_name: string;
  address: string;
  address_detail: Address;
  total_amount: string;
  delivery_fee: string;
  status: OrderStatus;
  can_be_cancelled: boolean;
  items: OrderItem[];
  delivery: Delivery;
  payment: {
    id: string;
    method: string;
    status: "pending" | "success" | "failed" | "refunded";
    refund: { id: number; status: Refund["status"]; amount: string; refunded_at: string | null } | null;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface CheckoutPayload {
  store: string;
  address: string;
  delivery_type: "pickup" | "standard" | "express";
  payment_method: "wave" | "orange_money" | "card";
  items: { product_variant: string; quantity: number }[];
}

export interface SalesStatistic {
  id: string;
  store: string;
  date: string;
  total_sales: string;
  total_orders: number;
  avg_order_value: string;
  created_at: string;
}

export interface StoreSummary {
  revenue_30d: string;
  orders_30d: number;
  avg_order_value_30d: string;
  delivered_rate: number;
  avg_rating: number | null;
  review_count: number;
}

export interface Notification {
  id: string;
  user: string;
  channel: string;
  subject: string;
  message: string;
  status: string;
  is_read: boolean;
  sent_at: string | null;
  created_at: string;
}

export interface SponsoredProduct {
  id: string;
  product: string;
  store: string;
  daily_budget: string;
  starts_at: string;
  ends_at: string;
  status: "active" | "inactive" | "expired";
  created_at: string;
  updated_at: string;
}

export interface SubscriptionPlan {
  id: string;
  name: string;
  price: string;
  billing_cycle: string;
  features: Record<string, unknown>;
  max_products: number | null;
  /** Taux de commission (en %) prélevé sur les ventes pendant la période. */
  commission_rate: string;
  /** Durée (jours) d'une période d'abonnement achetée une seule fois. */
  duration_days: number;
  /** Seuls les plans actifs sont proposés aux commerçants. */
  is_active: boolean;
  created_at: string;
}

export interface Subscription {
  id: string;
  plan: string;
  subscriber_type: string;
  subscriber_id: string;
  status: string;
  starts_at: string;
  ends_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Invoice {
  id: string;
  subscription: string;
  amount: string;
  status: string;
  issued_at: string;
  due_at: string | null;
  paid_at: string | null;
}

export interface Payment {
  id: string;
  order: string | null;
  subscription: string | null;
  method: "wave" | "orange_money" | "card";
  amount: string;
  status: "pending" | "success" | "failed" | "refunded";
  provider_ref: string;
  refund: { id: number; status: Refund["status"]; amount: string; refunded_at: string | null } | null;
  created_at: string;
}

export interface Refund {
  id: number;
  payment: string;
  order_id: string;
  store_name: string;
  customer_email: string;
  amount: string;
  reason: string;
  status: "pending" | "approved" | "rejected" | "completed";
  refunded_at: string | null;
  created_at: string;
}

/** Statut d'un dossier KYC (envoyé/par service via SellerKYC / DriverKYC). */
export type KycStatus = "PENDING" | "UNDER_REVIEW" | "VERIFIED" | "REJECTED";

/**
 * Dossier KYC vendeur ou livreur. Les identifiants propriétaire (`seller` /
 * `driver`) sont impartis par le backend : le frontend ne les choisit jamais.
 */
export type KycDocument =
  | KycDocumentBase<'seller', SellerKycOwner>
  | KycDocumentBase<'driver', DriverKycOwner>;

interface KycDocumentBase<TType extends "seller" | "driver", TOwner> {
  /** Identifiant du dossier KYC (UUID). */
  id: string;
  account_type: TType;
  owner: TOwner;
  document_type: string;
  /** Clé de stockage de la pièce — jamais une URL publique. */
  document_front: string;
  document_back: string;
  /** URL pré-signée à courte durée, générée par Django (admin uniquement). */
  document_front_url: string;
  document_back_url: string;
  status: KycStatus;
  rejection_reason: string | null;
  submitted_at: string | null;
  verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SellerKycOwner {
  id: string;
  name: string;
  email: string;
  phone: string;
}

export interface DriverKycOwner {
  id: string;
  name: string;
  email: string;
  phone: string;
}

export interface SellerKyc extends Omit<KycDocumentBase<"seller", SellerKycOwner>, "owner"> {
  seller: string;
  seller_name: string;
  seller_email: string;
  seller_phone: string;
}

export interface DriverKyc extends Omit<KycDocumentBase<"driver", DriverKycOwner>, "owner"> {
  driver: string;
  driver_name: string;
  driver_email: string;
  driver_phone: string;
}

/** Portefeuille vendeur — soldes toujours calculés côté backend (§9). */
export interface SellerWallet {
  seller: string;
  available_balance: string;
  pending_balance: string;
  total_earned: string;
  total_withdrawn: string;
}

export type WalletTransactionType = "sale" | "commission" | "refund" | "payout" | "release" | "adjustment";

/**
 * Ligne du ledger du portefeuille vendeur (§10) : chaque mouvement porte les
 * soldes (disponible / en attente) avant et après l'opération.
 */
export interface WalletTransaction {
  id: number;
  type: WalletTransactionType;
  amount: string;
  available_before: string;
  available_after: string;
  pending_before: string;
  pending_after: string;
  reference: string;
  order: string | null;
  description: string;
  created_at: string;
}

export type SellerCommissionStatus = "trial" | "active" | "expired" | "cancelled";

/** Entitlement commission du vendeur : essai, plan, taux figé applicable (§4, §12). */
export interface SellerCommissionSubscription {
  status: SellerCommissionStatus;
  plan: string;
  trial_ends_at: string | null;
  starts_at: string | null;
  ends_at: string | null;
  rate: string;
  can_sell: boolean;
}

/**
 * Vente ventilée par vendeur (§13) : brut, taux, commission et net (net + frais
 * de livraison) figés au moment de la vente — jamais recalculés après coup.
 */
export interface CommissionTransaction {
  id: string;
  order: string;
  order_number: string;
  store_name: string;
  customer_email: string;
  seller: string;
  plan: string;
  gross_amount: string;
  commission_rate: string;
  commission_amount: string;
  seller_amount: string;
  is_refunded: boolean;
  is_released: boolean;
  created_at: string;
  refunded_at: string | null;
  released_at: string | null;
}

/** Réponse des endpoints `commissions/wallet/me/` et `commissions/subscription/me/` (§23). */
export interface SellerFinanceDashboard {
  wallet: SellerWallet;
  subscription: SellerCommissionSubscription;
  recent_sales: CommissionTransaction[];
  recent_wallet_transactions: WalletTransaction[];
}

export type PayoutStatus = "pending" | "completed" | "rejected";

/** Demande de retrait du vendeur (§19) — ne porte que sur le solde disponible. */
export interface Payout {
  id: string;
  seller: string;
  amount: string;
  method: "wave" | "orange_money" | "card";
  status: PayoutStatus;
  reference: string;
  completed_at: string | null;
  created_at: string;
}

export interface CommissionStatsByPlan {
  plan: string;
  count: number;
  commissions: string;
  volume: string;
}

/** Statistiques admin de la plateforme (§25) — endpoint `commissions/commissions/stats/`. */
export interface CommissionStats {
  today_commissions: string;
  month_commissions: string;
  total_commissions: string;
  total_volume: string;
  total_to_sellers: string;
  total_refunded_commissions: string;
  total_payouts: string;
  platform_balance: string;
  platform_total_subscriptions: string;
  by_plan: CommissionStatsByPlan[];
}
