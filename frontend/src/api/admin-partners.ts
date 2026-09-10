import { apiGet, apiPatch, apiPost } from "@/lib/api";
import type { DeliveryPartner, DeliveryPartnerDetail, Paginated } from "@/types";

export async function listAdminPartners(params?: { page?: number }) {
  const qs = params?.page ? `?page=${params.page}` : "";
  const data = await apiGet<Paginated<DeliveryPartner>>(`/orders/partners/${qs}`);
  return data.results;
}

export function getAdminPartner(id: string) {
  return apiGet<DeliveryPartnerDetail>(`/orders/partners/${id}/`);
}

export function createAdminPartner(payload: {
  name: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  address: string;
  city: string;
}) {
  return apiPost<DeliveryPartner>("/orders/partners/", payload);
}

export function updateAdminPartner(id: string, payload: Partial<Pick<DeliveryPartner, "contact_name" | "contact_email" | "contact_phone" | "address" | "city">>) {
  return apiPatch<DeliveryPartner>(`/orders/partners/${id}/`, payload);
}

export function activateAdminPartner(id: string) {
  return apiPost<DeliveryPartnerDetail>(`/orders/partners/${id}/activate/`);
}

export function suspendAdminPartner(id: string) {
  return apiPost<DeliveryPartnerDetail>(`/orders/partners/${id}/suspend/`);
}

/** Régénère la clé d'API — le clair n'est renvoyé qu'une seule fois. */
export function rotateAdminPartnerApiKey(id: string) {
  return apiPost<{ api_key: string; api_key_last4: string }>(`/orders/partners/${id}/rotate-api-key/`);
}