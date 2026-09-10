import { apiGet, apiPatch, apiPost } from "@/lib/api";
import type { Delivery, DeliveryPartner, DeliveryPartnerDetail, Driver, Paginated, PartnerInvoice, PartnerSpaceStats, PartnerZonePricing } from "@/types";

/** Profil de l'entreprise partenaire (détail + statistiques). */
export function getPartnerProfile() {
  return apiGet<DeliveryPartnerDetail>("/orders/partner/profile/");
}

export function updatePartnerProfile(payload: Partial<Pick<DeliveryPartner, "contact_name" | "contact_email" | "contact_phone" | "address" | "city">>) {
  return apiPatch<DeliveryPartnerDetail>("/orders/partner/profile/", payload);
}

/** Régénère la clé d'API d'intégration — le clair n'est rendu qu'une seule fois. */
export function rotatePartnerApiKey() {
  return apiPost<{ api_key: string; api_key_last4: string }>("/orders/partner/api-key/");
}

export function getPartnerBankInfo() {
  return apiGet<{ method: string; iban: string; provider: string }>("/orders/partner/banks/");
}

/** Tableau de bord (spec §6) : volumes, taux, revenus, impayés. */
export function getPartnerStats() {
  return apiGet<PartnerSpaceStats>("/orders/partner/stats/");
}

export function listPartnerDeliveries(status?: string) {
  return apiGet<Delivery[]>(`/orders/partner/deliveries/${status ? `?status=${encodeURIComponent(status)}` : ""}`);
}

export function listPartnerInvoices() {
  return apiGet<PartnerInvoice[]>("/orders/partner/invoices/");
}

export function getPartnerInvoice(id: string) {
  return apiGet<PartnerInvoice>(`/orders/partner/invoices/${id}/`);
}

export function listPartnerZones() {
  return apiGet<PartnerZonePricing[]>("/orders/partner/zones/");
}

export function updatePartnerZone(id: string, payload: Partial<Pick<PartnerZonePricing, "client_fee" | "partner_cost" | "estimated_delay_minutes" | "max_weight_kg" | "is_available">>) {
  return apiPatch<PartnerZonePricing>(`/orders/partner/zones/${id}/`, payload);
}

/** Livreurs de SA propre entreprise (le backend scope par compte partenaire). */
export async function listCompanyDrivers() {
  const data = await apiGet<Paginated<Driver>>("/orders/drivers/");
  return data.results;
}

/** Crée un compte livreur rattaché à l'entreprise (mot de passe provisoire renvoyé une seule fois). */
export function createCompanyDriver(payload: {
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  vehicle_type: string;
}) {
  return apiPost<Driver & { temporary_password: string }>("/orders/drivers/register/", payload);
}

/** Suspend / réactive un livreur (capacité, disponibilité). */
export function updateCompanyDriver(
  id: string,
  payload: Partial<Pick<Driver, "is_suspended" | "max_active_deliveries" | "vehicle_type">>,
) {
  return apiPatch<Driver>(`/orders/drivers/${id}/`, payload);
}