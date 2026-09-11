import { API_BASE_URL, apiGet, apiPatch, apiPost } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { Address, CheckoutPayload, Delivery, DeliveryEvent, DeliveryQuote, DeliveryStatus, Driver, DriverAvailability, GlobalOrder, Order, Paginated } from "@/types";

export async function listAddresses() {
  const data = await apiGet<Paginated<Address>>("/orders/addresses/");
  return data.results;
}

export function createAddress(payload: {
  label: string;
  street: string;
  city: string;
  country: string;
  latitude?: number;
  longitude?: number;
}) {
  return apiPost<Address>("/orders/addresses/", payload);
}

export async function listOrders() {
  const data = await apiGet<Paginated<Order>>("/orders/");
  return data.results;
}

/** Comme `listOrders`, mais renvoie l'enveloppe de pagination DRF complète, pour la vue d'ensemble admin. */
export function listOrdersPaginated(params?: { page?: number }) {
  const qs = params?.page ? `?page=${params.page}` : "";
  return apiGet<Paginated<Order>>(`/orders/${qs}`);
}

export function getOrder(id: string) {
  return apiGet<Order>(`/orders/${id}/`);
}

/** Commandes globales multi-boutiques du client courant. */
export async function listGlobalOrders() {
  const data = await apiGet<Paginated<GlobalOrder>>("/orders/global-orders/");
  return data.results;
}

export function getGlobalOrder(id: string) {
  return apiGet<GlobalOrder>(`/orders/global-orders/${id}/`);
}

export function cancelGlobalOrder(id: string) {
  return apiPost<GlobalOrder>(`/orders/global-orders/${id}/cancel/`);
}

/** Crée la commande. Sans `store` dans le payload (multi-boutiques), le
 * backend déduit les boutiques des articles et renvoie une `GlobalOrder`. */
export function checkout(payload: CheckoutPayload) {
  return apiPost<Order | GlobalOrder>("/orders/checkout/", payload);
}

export function cancelOrder(id: string) {
  return apiPost<Order>(`/orders/${id}/cancel/`);
}

/** Suivi de commande sans connexion (invité) — par référence ou id + email
 * (POST /orders/track/, spec §16 « achat sans compte »). */
export function trackOrder(reference: string, email: string) {
  return apiPost<Order | GlobalOrder>("/orders/track/", { reference, email }, { auth: false });
}

/** Tarif de livraison côté serveur AVANT paiement, pour un panier
 * multi-boutiques (frais de collecte + distance réellement calculés et
 * affichés ; jamais calculés dans le navigateur). */
export async function deliveryCalculate(payload: {
  items: { product_variant: string; quantity: number }[];
  address: string;
  delivery_type: "pickup" | "standard" | "express";
}) {
  return apiPost<DeliveryQuote>("/orders/delivery-calculate/", payload);
}

export async function getDeliveryQuote(payload: {
  store: string;
  address: string;
  delivery_type: "pickup" | "standard" | "express";
}) {
  const data = await apiPost<{ delivery_fee: string }>("/orders/quote/", payload);
  return parseFloat(data.delivery_fee);
}

export async function listAvailableDrivers(storeId?: string) {
  const data = await apiGet<Paginated<Driver> | Driver[]>(
    `/orders/drivers/${storeId ? `?store=${storeId}` : ""}`,
  );
  return Array.isArray(data) ? data : data.results;
}

export async function registerDriver(payload: {
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  vehicle_type: string;
}) {
  return apiPost<Driver & { temporary_password: string }>("/orders/drivers/register/", payload);
}

export function updateMyDriverPosition(latitude: number | string, longitude: number | string) {
  return apiPost<Driver>("/orders/drivers/me/position/", { latitude, longitude });
}

export function getMyDriverProfile() {
  return apiGet<Driver>("/orders/drivers/me/");
}

export function updateMyDriverProfile(payload: { vehicle_type?: string; availability_status?: DriverAvailability }) {
  return apiPatch<Driver>("/orders/drivers/me/", payload);
}

export async function listDeliveries() {
  const data = await apiGet<Paginated<Delivery>>("/orders/deliveries/");
  return data.results;
}

export function getDelivery(id: string) {
  return apiGet<Delivery>(`/orders/deliveries/${id}/`);
}

export function assignDriver(deliveryId: string, driverId: string) {
  return apiPost<Delivery>(`/orders/deliveries/${deliveryId}/assign/`, { driver: driverId });
}

/** Meilleurs livreurs candidats pour une livraison donnée (Espace Partenaire). */
export async function suggestDrivers(deliveryId: string, limit = 5) {
  return apiGet<{ drivers: Driver[]; message?: string }>(`/orders/deliveries/${deliveryId}/suggest/?limit=${limit}`);
}

/** Le livreur accepte la mission qui lui est affectée. */
export function acceptDelivery(deliveryId: string) {
  return apiPost<Delivery>(`/orders/deliveries/${deliveryId}/accept/`);
}

/** Le livreur refuse la mission (motif obligatoire) — redevient affectable. */
export function refuseDelivery(deliveryId: string, reason: string, comment = "") {
  return apiPost<Delivery>(`/orders/deliveries/${deliveryId}/refuse/`, { reason, comment });
}

/** Le livreur signale un échec de livraison (motif + commentaire obligatoires). */
export function failDelivery(deliveryId: string, reason: string, comment = "") {
  return apiPost<Delivery>(`/orders/deliveries/${deliveryId}/fail/`, { reason, comment });
}

/** Demande de retour du colis au vendeur. */
export function requestDeliveryReturn(deliveryId: string, reason: string, comment = "") {
  return apiPost<Delivery>(`/orders/deliveries/${deliveryId}/return/`, { reason, comment });
}

/** Le retour est terminé : colis rendu au vendeur. */
export function completeDeliveryReturn(deliveryId: string, comment = "") {
  return apiPost<Delivery>(`/orders/deliveries/${deliveryId}/return/complete/`, { comment });
}

/** Timeline complète (spec §28) — pour l'Espace Partenaire / livreur. */
export function deliveryEventsHistory(deliveryId: string) {
  return apiGet<DeliveryEvent[]>(`/orders/deliveries/${deliveryId}/events-history/`);
}

export function updateDeliveryStatus(deliveryId: string, status: DeliveryStatus) {
  return apiPost<Delivery & { confirmation_code?: string }>(`/orders/deliveries/${deliveryId}/status/`, { status });
}

/** Le client (ou l'admin) valide la réception avec le code OTP remis par le livreur. */
export function confirmDelivery(deliveryId: string, code: string) {
  return apiPost<Delivery>(`/orders/deliveries/${deliveryId}/confirm/`, { code });
}

/** Le livreur affecté (ou l'admin) régénère le code de confirmation (perdu/expiré). */
export function regenerateDeliveryOtp(deliveryId: string) {
  return apiPost<Delivery & { confirmation_code: string }>(`/orders/deliveries/${deliveryId}/regenerate-otp/`);
}

export function shareDeliveryPosition(deliveryId: string, latitude: number, longitude: number) {
  return apiPost(`/orders/deliveries/${deliveryId}/track/`, { latitude, longitude });
}

/**
 * Abonne la page au flux temps réel (SSE) d'une livraison : positions GPS et
 * changements de statut arrivent en push, sans polling.
 *
 * Le `<EventSource>` navigateur ne pouvant pas poser d'en-tête `Authorization`,
 * on passe le JWT en query string (le backend l'accepte via `?access_token=`).
 * Appeler `source.close()` dans l'effet pour fermer proprement le flux.
 */
export function subscribeDeliveryEvents(deliveryId: string, onEvent: (event: DeliveryEvent) => void) {
  const token = useAuthStore.getState().accessToken;
  const query = token ? `?access_token=${encodeURIComponent(token)}` : "";
  const source = new EventSource(`${API_BASE_URL}/orders/deliveries/${deliveryId}/events/${query}`);
  source.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data) as DeliveryEvent);
    } catch {
      // Chunk de contrôle (heartbeat `: keep-alive` ou malformé) : ignoré.
    }
  };
  return source;
}
