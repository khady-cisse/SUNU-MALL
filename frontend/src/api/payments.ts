import { apiGet, apiPost } from "@/lib/api";
import type { Paginated, Payment, Refund } from "@/types";

export function listPayments(params?: { page?: number }) {
  const qs = params?.page ? `?page=${params.page}` : "";
  return apiGet<Paginated<Payment>>(`/payments/${qs}`);
}

export function listRefunds(params?: { page?: number; status?: string }) {
  const qs = new URLSearchParams();
  if (params?.page) qs.set("page", String(params.page));
  if (params?.status) qs.set("status", params.status);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiGet<Paginated<Refund>>(`/payments/refunds/${suffix}`);
}

export function processRefund(refundId: number) {
  return apiPost<Refund>(`/payments/refunds/${refundId}/process/`);
}

export interface InitiatePaymentResult {
  sandbox: boolean;
  provider_ref: string;
  message: string;
}

export function initiatePayment(paymentId: string) {
  return apiPost<InitiatePaymentResult>(`/payments/${paymentId}/initiate/`);
}

export function sandboxConfirmPayment(paymentId: string, outcome: "success" | "failed") {
  return apiPost<Payment>(`/payments/${paymentId}/sandbox-confirm/`, { outcome });
}
