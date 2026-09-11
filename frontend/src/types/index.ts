export type Role =
  | "admin"
  | "super_admin"
  | "admin_kyc"
  | "admin_support"
  | "admin_finance"
  | "admin_marketplace"
  | "admin_delivery"
  | "merchant"
  | "client"
  | "driver"
  | "partner";

/** Rôles d'administration du centre de contrôle (doivent matcher backend Role.ADMIN_ROLES). */
export const ADMIN_ROLES: Role[] = [
  "admin",
  "super_admin",
  "admin_kyc",
  "admin_support",
  "admin_finance",
  "admin_marketplace",
  "admin_delivery",
];

export function isAdminRole(roles: Role[]): boolean {
  return roles.some((role) => ADMIN_ROLES.includes(role));
}

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
  /** Identité du propriétaire vérifiée par l'admin (SellerKYC VERIFIED). */
  is_verified_seller: boolean;
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
  /** Boutique du propriétaire vérifiée KYC — badge "Vérifié" sur les cartes. */
  store_is_verified?: boolean;
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
  /** Entreprise partenaire à laquelle appartient le livreur (null = libre). */
  partner: string | null;
  is_suspended: boolean;
  /** Capacité maximale de livraisons actives simultanées. */
  max_active_deliveries: number;
  created_at: string;
  updated_at: string;
}

/** Chaîne d'états 2025 (spec §5, §16-§18) : toutes les étapes sont horodatées. */
export type DeliveryStatus =
  | "pending"
  | "assigned"
  | "accepted"
  | "pickup_pending"
  | "picked_up"
  | "in_transit"
  | "out_for_delivery"
  | "delivered"
  | "delivery_failed"
  | "customer_unavailable"
  | "return_requested"
  | "returned"
  | "cancelled";

export type DeliveryFailureReason =
  | "customer_absent"
  | "number_unreachable"
  | "wrong_address"
  | "customer_refused"
  | "package_damaged"
  | "transport_issue"
  | "other";

export type DeliveryReturnReason =
  | "customer_absent"
  | "customer_refused"
  | "wrong_address"
  | "package_damaged"
  | "shipping_error"
  | "other";

/** Étape d'historique renvoyée par `DeliverySerializer.timeline`. */
export interface DeliveryTimelineEntry {
  action: string;
  actor_role: string;
  previous_status: string | null;
  new_status: string | null;
  comment: string;
  created_at: string;
}

export interface DeliveryTrackingPoint {
  latitude: string;
  longitude: string;
  recorded_at: string;
}

export interface DeliveryPickup {
  id: string;
  store: string;
  store_name: string;
  address: string;
  city: string;
  latitude: string | null;
  longitude: string | null;
  package_count: number;
  pickup_status: "pending" | "ready" | "picked_up";
  pickup_order: number;
  picked_up_at: string | null;
  notes: string;
}

export interface Delivery {
  id: string;
  /** Référence lisible DLV-YYYYMMDD-XXXXXX. */
  reference: string;
  order: string | null;
  /** Commande globale multi-boutiques (nullable sur les missions classiques). */
  global_order: string | null;
  driver: string | null;
  driver_detail: Driver | null;
  /** Entreprise partenaire en charge (spec §2). */
  partner: string | null;
  partner_detail: { id: string; name: string; phone: string } | null;
  status: DeliveryStatus;
  timeline: DeliveryTimelineEntry[];
  picked_up_at: string | null;
  delivered_at: string | null;
  last_position: DeliveryTrackingPoint | null;
  eta_seconds: number | null;
  /** Points de collecte (mission multi-boutiques) — vide sur les courses simples. */
  pickups: DeliveryPickup[];
  pickups_collected: number;
  pickups_total: number;
  /** Tarif facturé au client, coût partenaire et marge Sunu Mall (read-only). */
  total_delivery_fee?: string;
  partner_cost?: string;
  platform_margin?: string;
  total_distance?: string | null;
  /** Preuve de livraison (spec §20). */
  proof_method: string | null;
  proof_note: string;
  proof_photo: string | null;
  proof_latitude: string | null;
  proof_longitude: string | null;
  proof_recorded_at: string | null;
  /** Motifs d'échec / de refus / de retour (spec §16-§18). */
  failure_reason: DeliveryFailureReason | "";
  failure_comment: string;
  return_reason: DeliveryReturnReason | "";
  refuse_reason: string;
  created_at: string;
  updated_at: string;
}

/** Commande globale multi-boutiques (spec multi-boutiques) : un panier, N
 * boutiques, un seul paiement (Payment.global_order). Chaque `orders` est une
 * sous-commande visible uniquement par le vendeur concerné (isolation §11). */
export interface GlobalOrder {
  id: string;
  reference: string;
  customer: string;
  address: string;
  address_detail: Address;
  delivery_type: "pickup" | "standard" | "express";
  items_total: string;
  delivery_fee: string;
  total_amount: string;
  status: "pending" | "paid" | "cancelled";
  number_of_stores: number;
  number_of_pickups: number;
  orders: (Order & { delivery: null; delivery_fee: string; global_order: string })[];
  delivery: Delivery;
  payment:
    | {
        id: string;
        method: string;
        status: "pending" | "success" | "failed" | "refunded";
        refund: { id: number; status: Refund["status"]; amount: string; refunded_at: string | null } | null;
      }
    | null;
  created_at: string;
  updated_at: string;
}

/** Réponse de `GET/POST /orders/delivery-calculate/` (tarif pré-paiement). */
export interface DeliveryQuote {
  number_of_stores: number;
  number_of_pickups: number;
  distance: number | null;
  delivery_fee: string;
  currency: string;
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
  store_address: string;
  store_city: string;
  store_latitude: string | null;
  store_longitude: string | null;
  address: string;
  address_detail: Address;
  total_amount: string;
  delivery_fee: string;
  delivery_type?: "pickup" | "standard" | "express";
  /** Identifiant de la commande globale multi-boutiques (null sinon). */
  global_order: string | null;
  status: OrderStatus;
  can_be_cancelled: boolean;
  items: OrderItem[];
  delivery: Delivery | null;
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
  /** Optionnel : fourni pour une commande « une boutique » classique ; omis
   * pour une commande globale multi-boutiques (les boutiques sont déduites
   * des articles par le backend — jamais confiées au client). */
  store?: string | null;
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
  metadata?: Record<string, unknown>;
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
  /** Clé métier stable (STARTER / PRO / BUSINESS) — jamais renommée. */
  code: string;
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

export type SubscriptionStatus = "pending" | "active" | "cancelled" | "expired" | "suspended";

export interface Subscription {
  id: string;
  /** Référence publique lisible, ex. SUB-20260909-A1B2C3. */
  reference: string;
  plan: string;
  plan_code: string;
  plan_name: string;
  subscriber_type: string;
  subscriber_id: string;
  status: SubscriptionStatus;
  starts_at: string;
  ends_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Événement immuable du cycle de vie d'un abonnement (activation, renouvellement, changement de formule…). */
export interface SubscriptionHistory {
  id: number;
  subscription: string;
  action:
    | "created"
    | "activated"
    | "renewed"
    | "plan_changed"
    | "expired"
    | "cancelled"
    | "suspended";
  old_plan_name: string | null;
  new_plan_name: string | null;
  old_end_date: string | null;
  new_end_date: string | null;
  performed_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export type SupportTicketStatus = "new" | "open" | "answered" | "resolved" | "closed";

export interface SupportTicket {
  id: string;
  /** Référence publique lisible, ex. TKT-20260909-000125. */
  reference: string;
  requester: string;
  requester_name: string;
  category: string;
  subject: string;
  description: string;
  status: SupportTicketStatus;
  assigned_to: string | null;
  assigned_to_name: string | null;
  created_at: string;
  updated_at: string;
  messages: TicketMessage[];
}

export interface TicketMessage {
  id: number;
  ticket: string;
  author: string | null;
  body: string;
  is_support_reply: boolean;
  created_at: string;
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
export type KycStatus = "PENDING" | "SUBMITTED" | "UNDER_REVIEW" | "VERIFIED" | "REJECTED" | "SUSPENDED" | "BLOCKED";

/** Historique des changements de statut d'un dossier (visible admin). */
export interface KycHistoryEntry {
  previous_status: KycStatus;
  new_status: KycStatus;
  reason: string;
  reviewed_by: string;
  reviewed_by_name: string;
  created_at: string;
}

/** Alerte de fraude calculée côté backend à partir des recoupements en base. */
export interface FraudFlag {
  code: "document_reused" | "phone_reused";
  message: string;
}

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
  /** Adresse d'exercice déclarée à la soumission (vendeur uniquement). */
  address: string;
  is_verified_seller: boolean;
  can_sell: boolean;
  /** Admin uniquement : le vendeur reçoit toujours une liste vide. */
  fraud_flags: FraudFlag[];
  /** Admin uniquement : historique des changements de statut. */
  history: KycHistoryEntry[];
}

export interface DriverKyc extends Omit<KycDocumentBase<"driver", DriverKycOwner>, "owner"> {
  driver: string;
  driver_name: string;
  driver_email: string;
  driver_phone: string;
  is_verified_driver: boolean;
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

export type PartnerStatus = "inactive" | "active" | "suspended";

/** Entreprise partenaire logistique (spec §2). */
export interface DeliveryPartner {
  id: string;
  name: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  address: string;
  city: string;
  status: PartnerStatus;
  /** Score automatique 0-100 (calculé côté serveur, en lecture seule). */
  score: number;
  created_at: string;
  updated_at: string;
}

/** Détail entreprise (route `retrieve` admin / profil partenaire). */
export interface DeliveryPartnerDetail extends DeliveryPartner {
  drivers_count: number;
  deliveries_count: number;
  delivered_count: number;
  success_rate: number;
  return_rate: number;
  active_zones: { id: string; name: string; client_fee: string }[];
}

/** Tarif d'un partenaire pour une zone (spec §21-§22). */
export interface PartnerZonePricing {
  id: string;
  partner: string;
  zone: string;
  zone_name: string;
  /** Facturé au client (frais de livraison). */
  client_fee: string;
  /** Versé au partenaire. */
  partner_cost: string;
  estimated_delay_minutes: number;
  max_weight_kg: string;
  is_available: boolean;
  /** Marge Sunu Mall = client_fee - partner_cost (calculée côté serveur). */
  margin: string;
}

export type PartnerInvoiceStatus = "draft" | "pending" | "paid" | "contested";

/** Facture mensuelle du partenaire (spec §19-§22). */
export interface PartnerInvoice {
  id: string;
  partner: string;
  reference: string;
  status: PartnerInvoiceStatus;
  period_start: string;
  period_end: string;
  due_date: string | null;
  marketplace_rate: string;
  on_demand_rate: string;
  marketplace_deliveries_count: number;
  on_demand_deliveries_count: number;
  marketplace_amount: string;
  on_demand_amount: string;
  collection_fees: string;
  total_due: string;
  balance: string;
  recon_amount: string;
  recon_diff: string;
  recon_date: string | null;
  paid_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Réponse du tableau de bord partenaire (`/orders/partner/stats/`). */
export interface PartnerSpaceStats {
  period_start: string;
  deliveries_total: number;
  deliveries_in_progress: number;
  deliveries_delivered: number;
  deliveries_failed: number;
  deliveries_returned: number;
  deliveries_month: number;
  success_rate: number;
  return_rate: number;
  avg_delay_minutes: number;
  active_drivers: number;
  total_revenue: string;
  unpaid_amount: string;
}
