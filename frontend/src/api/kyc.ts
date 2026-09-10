import { apiGet, apiPost } from "@/lib/api";
import type { KycStatus, Paginated, SellerKyc, DriverKyc } from "@/types";

/**
 * API KYC (vendeurs / livreurs).
 *
 * Le propriétaire d'un dossier est toujours le compte connecté : les
 * fonctions de soumission n'acceptent QUE les documents + le type de
 * document. Les URLs de pièces (`document_front_url` / `document_back_url`)
 * sont des URLs pré-signées à courte durée générées par Django pour l'admin —
 * le frontend ne manipule jamais directement les objets MinIO.
 */

export interface SubmitKycResult {
  id: string;
  status: KycStatus;
}

export function listSellerKycs(params?: { page?: number; status?: KycStatus }) {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.status) query.set("status", params.status);
  const qs = query.toString();
  return apiGet<Paginated<SellerKyc>>(`/kyc/seller-kyc/${qs ? `?${qs}` : ""}`);
}

export function listDriverKycs(params?: { page?: number; status?: KycStatus }) {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.status) query.set("status", params.status);
  const qs = query.toString();
  return apiGet<Paginated<DriverKyc>>(`/kyc/driver-kyc/${qs ? `?${qs}` : ""}`);
}

export function getSellerKyc(id: string) {
  return apiGet<SellerKyc>(`/kyc/seller-kyc/${id}/`);
}

export function getDriverKyc(id: string) {
  return apiGet<DriverKyc>(`/kyc/driver-kyc/${id}/`);
}

export function approveSellerKyc(id: string) {
  return apiPost<SellerKyc>(`/kyc/seller-kyc/${id}/approve/`);
}

export function approveDriverKyc(id: string) {
  return apiPost<DriverKyc>(`/kyc/driver-kyc/${id}/approve/`);
}

export function rejectSellerKyc(id: string, reason: string) {
  return apiPost<SellerKyc>(`/kyc/seller-kyc/${id}/reject/`, { reason });
}

export function rejectDriverKyc(id: string, reason: string) {
  return apiPost<DriverKyc>(`/kyc/driver-kyc/${id}/reject/`, { reason });
}

/** Passe le dossier en "examen en cours" (réservé admin). */
export function startReviewSellerKyc(id: string) {
  return apiPost<SellerKyc>(`/kyc/seller-kyc/${id}/start-review/`);
}

export function startReviewDriverKyc(id: string) {
  return apiPost<DriverKyc>(`/kyc/driver-kyc/${id}/start-review/`);
}

/** Demande une nouvelle soumission : le dossier repasse en REJECTED. */
export function requestResubmissionSellerKyc(id: string, reason: string) {
  return apiPost<SellerKyc>(`/kyc/seller-kyc/${id}/request-resubmission/`, { reason });
}

export function requestResubmissionDriverKyc(id: string, reason: string) {
  return apiPost<DriverKyc>(`/kyc/driver-kyc/${id}/request-resubmission/`, { reason });
}

/** Suspend le compte vendeur/livreur (ventes coupées, re-soumission possible). */
export function suspendSellerKyc(id: string, reason?: string) {
  return apiPost<SellerKyc>(`/kyc/seller-kyc/${id}/suspend/`, { reason: reason ?? "" });
}

export function suspendDriverKyc(id: string, reason?: string) {
  return apiPost<DriverKyc>(`/kyc/driver-kyc/${id}/suspend/`, { reason: reason ?? "" });
}

/** Bloque définitivement le compte (ventes coupées, aucun retrait possible). */
export function blockSellerKyc(id: string, reason?: string) {
  return apiPost<SellerKyc>(`/kyc/seller-kyc/${id}/block/`, { reason: reason ?? "" });
}

export function blockDriverKyc(id: string, reason?: string) {
  return apiPost<DriverKyc>(`/kyc/driver-kyc/${id}/block/`, { reason: reason ?? "" });
}

/** Récupère son propre dossier vendeur (404 si jamais soumis). */
export function getMySellerKyc() {
  return apiGet<SellerKyc>("/kyc/seller-kyc/me/");
}

/** Récupère son propre dossier livreur (404 si jamais soumis). */
export function getMyDriverKyc() {
  return apiGet<DriverKyc>("/kyc/driver-kyc/me/");
}

export function submitSellerKyc(form: FormData) {
  return apiPost<SubmitKycResult>("/kyc/seller-kyc/submit/", form);
}

export function submitDriverKyc(form: FormData) {
  return apiPost<SubmitKycResult>("/kyc/driver-kyc/submit/", form);
}