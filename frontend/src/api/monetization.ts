import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api";
import type { Invoice, Notification, Paginated, Payment, SponsoredProduct, Subscription, SubscriptionHistory, SubscriptionPlan } from "@/types";

export async function listNotifications() {
  const data = await apiGet<Paginated<Notification>>("/monetization/notifications/");
  return data.results;
}

export function markNotificationRead(id: string) {
  return apiPost<Notification>(`/monetization/notifications/${id}/read/`);
}

export function markAllNotificationsRead() {
  return apiPost<void>("/monetization/notifications/read-all/");
}

export async function listSubscriptionPlans() {
  const data = await apiGet<Paginated<SubscriptionPlan>>("/monetization/subscription-plans/");
  return data.results;
}

export async function listSubscriptions() {
  const data = await apiGet<Paginated<Subscription>>("/monetization/subscriptions/");
  return data.results;
}

export interface SubscriptionState {
  subscription: (Subscription & { plan_code: string; plan_name: string; days_left: number; is_active: boolean; in_grace: boolean; price: string; billing_cycle: string }) | null;
  has_active_subscription: boolean;
  product_limit: number | null;
  product_count: number;
  products_remaining: number | null;
  is_unlimited: boolean;
  grace_period_days: number;
}

/** État complet « Mon abonnement » (formule, dates, limites produits). */
export async function getMySubscriptionState() {
  return apiGet<SubscriptionState>("/monetization/subscription/me/");
}

/**
 * Crée l'abonnement (en attente) et son paiement associé. Le paiement est
 * `null` pour une offre gratuite, déjà activée directement côté serveur.
 */
export function subscribe(planId: string, paymentMethod: "wave" | "orange_money" | "card" = "wave") {
  return apiPost<{ subscription: Subscription; payment: Payment | null }>(
    `/monetization/subscription-plans/${planId}/subscribe/`,
    { payment_method: paymentMethod },
  );
}

export function cancelSubscription(id: string) {
  return apiPost<Subscription>(`/monetization/subscriptions/${id}/cancel/`);
}

/**
 * Prépare le renouvellement de la formule courante : un paiement en attente
 * est créé (jamais d'activation directe) puis confirmé via le webhook/sandbox.
 */
export function renewSubscription(paymentMethod: "wave" | "orange_money" | "card" = "wave") {
  return apiPost<{ payment: Payment }>("/monetization/subscriptions/renew/", { payment_method: paymentMethod });
}

/**
 * Monte/descend de formule : un paiement en attente est créé pour le nouveau
 * plan ; le changement n'est appliqué qu'après confirmation backend du paiement.
 */
export function changePlan(planCode: string, paymentMethod: "wave" | "orange_money" | "card" = "wave") {
  return apiPost<{ payment: Payment }>("/monetization/subscriptions/change-plan/", {
    plan_code: planCode,
    payment_method: paymentMethod,
  });
}

/** Historique immuable du cycle de vie de l'abonnement du vendeur. */
export async function listSubscriptionHistory() {
  return apiGet<SubscriptionHistory[]>("/monetization/subscriptions/history/");
}

/** Paiements d'abonnement du vendeur (souscription, renouvellement, changement). */
export async function listSubscriptionPayments() {
  return apiGet<Payment[]>("/monetization/subscriptions/payments/");
}

export async function listInvoices() {
  const data = await apiGet<Paginated<Invoice>>("/monetization/invoices/");
  return data.results;
}

export async function listMySponsoredProducts() {
  const data = await apiGet<Paginated<SponsoredProduct>>("/monetization/sponsored-products/");
  return data.results;
}

export function createSponsoredProduct(payload: {
  product: string;
  store: string;
  daily_budget: number;
  starts_at: string;
  ends_at: string;
}) {
  return apiPost<SponsoredProduct>("/monetization/sponsored-products/", { ...payload, status: "active" });
}

export function stopSponsoredProduct(id: string) {
  return apiPatch<SponsoredProduct>(`/monetization/sponsored-products/${id}/`, { status: "inactive" });
}

export function deleteSponsoredProduct(id: string) {
  return apiDelete<void>(`/monetization/sponsored-products/${id}/`);
}
