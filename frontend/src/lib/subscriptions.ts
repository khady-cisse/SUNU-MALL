/**
 * Helpers purs d'abonnement vendeur (affichage dashboard & cartes de plans).
 * Séparés du composant pour être unit-testables (vitest, `*.test.ts`) sans DOM.
 */
import type { SubscriptionPlan, SubscriptionStatus } from "@/types";

export const PLAN_LABEL: Record<string, string> = {
  STARTER: "Starter",
  PRO: "Pro",
  BUSINESS: "Business",
};

export const PLAN_BLURB: Record<string, string> = {
  STARTER: "Pour démarrer votre boutique en ligne.",
  PRO: "Pour développer vos ventes avec des statistiques avancées.",
  BUSINESS: "Pour les plus grandes boutiques : produits illimités.",
};

export const SUBSCRIPTION_STATUS_LABEL: Record<SubscriptionStatus, string> = {
  pending: "En attente de paiement",
  active: "Actif",
  cancelled: "Annulé",
  expired: "Expiré",
  suspended: "Suspendu",
};

export const SUBSCRIPTION_ACTION_LABEL: Record<string, string> = {
  created: "Souscription",
  activated: "Activé",
  renewed: "Renouvellement",
  plan_changed: "Changement de formule",
  expired: "Expiration",
  cancelled: "Annulation",
  suspended: "Suspension",
};

/** Variante Badge selon le statut d'un abonnement. */
export function subscriptionStatusVariant(status: string | undefined): "default" | "success" | "warning" | "danger" {
  switch (status) {
    case "active":
      return "success";
    case "pending":
    case "expired":
      return "warning";
    case "cancelled":
    case "suspended":
      return "danger";
    default:
      return "default";
  }
}

/** Libellé du cycle de facturation, ex. « / mois ». */
export function billingCycleSuffix(billingCycle: string | undefined) {
  return billingCycle === "yearly" ? "/ an" : "/ mois";
}

/** Date courte française, ex. « 09/09/2026 ». */
export function formatDateShort(dateStr: string | null | undefined) {
  if (!dateStr) return "—";
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "short" }).format(new Date(dateStr));
}

/** Vrai si la période de grâce est active (abonnement échu mais toujours vendable). */
export function isInGrace(
  subscription: { status: SubscriptionStatus | string; is_active?: boolean } | null | undefined,
) {
  return !!subscription && (subscription.status === "active" || subscription.status === "expired") && subscription.is_active === false;
}

export function planLabel(name: string) {
  return PLAN_LABEL[name] ?? name;
}

/** Libellé des produits selon la limite de la formule (null = illimité). */
export function productLimitLabel(maxProducts: number | null | undefined) {
  if (maxProducts == null) return "Produits illimités";
  return `${maxProducts} produits`;
}

/** « Actif » / encore valide : l'abonnement est ACTIVE et dans sa fenêtre. */
export function isActiveStatus(status: string | undefined) {
  return status === "active";
}

/** Nombre de jours pleins restants avant la date donnée (>= 0). */
export function daysUntil(dateStr: string | null | undefined) {
  if (!dateStr) return 0;
  const ms = new Date(dateStr).getTime() - new Date().setHours(0, 0, 0, 0);
  return Math.max(0, Math.ceil(ms / (1000 * 60 * 60 * 24)));
}

/** Date longue française, ex. « 15 octobre 2026 ». */
export function formatDateOnly(dateStr: string) {
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "long" }).format(new Date(dateStr));
}

/** Libellé de l'échéance de la période d'abonnement. */
export function periodSuffix(billingCycle: string | undefined) {
  return billingCycle === "yearly" ? "/ an" : " / mois";
}

/** La formule du catalogue qui correspond à l'abonnement courant, si trouvée. */
export function findPlanForSubscription(
  plans: SubscriptionPlan[] | undefined,
  subscriptionPlanId: string | undefined,
) {
  if (!plans || !subscriptionPlanId) return null;
  return plans.find((p) => p.id === subscriptionPlanId) ?? null;
}

/** Nombre de produits utilisés / restants pour l'affichage, null si illimité. */
export function productsRemaining(
  productCount: number | undefined,
  limit: number | null | undefined,
) {
  if (limit == null) return null;
  return Math.max(0, (limit ?? 0) - (productCount ?? 0));
}
