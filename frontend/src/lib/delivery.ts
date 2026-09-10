import type { DeliveryFailureReason, DeliveryReturnReason, DeliveryStatus } from "@/types";

export type StatusVariant = "default" | "success" | "warning" | "danger";

export const DELIVERY_STATUS_LABEL: Record<DeliveryStatus, string> = {
  pending: "En attente d'affectation",
  assigned: "Affectée",
  accepted: "Acceptée",
  pickup_pending: "En route vers la boutique",
  picked_up: "Colis récupéré",
  in_transit: "En transit",
  out_for_delivery: "En livraison",
  delivered: "Livrée",
  delivery_failed: "Échec de livraison",
  customer_unavailable: "Client indisponible",
  return_requested: "Retour demandé",
  returned: "Retournée",
  cancelled: "Annulée",
};

export const DELIVERY_STATUS_VARIANT: Record<DeliveryStatus, StatusVariant> = {
  pending: "default",
  assigned: "warning",
  accepted: "warning",
  pickup_pending: "warning",
  picked_up: "warning",
  in_transit: "warning",
  out_for_delivery: "warning",
  delivered: "success",
  delivery_failed: "danger",
  customer_unavailable: "danger",
  return_requested: "warning",
  returned: "default",
  cancelled: "danger",
};

export const DELIVERY_FAILURE_REASONS: Record<DeliveryFailureReason, string> = {
  customer_absent: "Client absent",
  number_unreachable: "Numéro inaccessible",
  wrong_address: "Mauvaise adresse",
  customer_refused: "Client refuse",
  package_damaged: "Colis endommagé",
  transport_issue: "Problème de transport",
  other: "Autre",
};

export const DELIVERY_RETURN_REASONS: Record<DeliveryReturnReason, string> = {
  customer_absent: "Client absent",
  customer_refused: "Client refuse",
  wrong_address: "Mauvaise adresse",
  package_damaged: "Colis endommagé",
  shipping_error: "Erreur d'envoi",
  other: "Autre",
};

export function deliveryStatusLabel(status: DeliveryStatus): string {
  return DELIVERY_STATUS_LABEL[status] ?? status;
}

export function reasonLabel(reason: string): string {
  if (reason in DELIVERY_FAILURE_REASONS) return DELIVERY_FAILURE_REASONS[reason as DeliveryFailureReason];
  if (reason in DELIVERY_RETURN_REASONS) return DELIVERY_RETURN_REASONS[reason as DeliveryReturnReason];
  return reason;
}