import { apiGet, apiPost } from "@/lib/api";
import type { CommissionStats, CommissionTransaction, Paginated, Payout, SellerFinanceDashboard } from "@/types";

export function getSellerFinanceDashboard() {
  return apiGet<SellerFinanceDashboard>("/commissions/wallet/me/");
}

export function listCommissionTransactions(params?: {
  page?: number;
  seller?: string;
  plan?: string;
  date_from?: string;
  date_to?: string;
}) {
  const qs = new URLSearchParams();
  if (params?.page) qs.set("page", String(params.page));
  if (params?.seller) qs.set("seller", params.seller);
  if (params?.plan) qs.set("plan", params.plan);
  if (params?.date_from) qs.set("date_from", params.date_from);
  if (params?.date_to) qs.set("date_to", params.date_to);
  const query = qs.toString();
  return apiGet<Paginated<CommissionTransaction>>(`/commissions/commissions/${query ? `?${query}` : ""}`);
}

export function getCommissionStats() {
  return apiGet<CommissionStats>("/commissions/commissions/stats/");
}

export function listPayouts(params?: { page?: number }) {
  const qs = params?.page ? `?page=${params.page}` : "";
  return apiGet<Paginated<Payout>>(`/commissions/payouts/${qs}`);
}

export function createPayout(amount: string | number, method: "wave" | "orange_money" | "card" = "wave") {
  return apiPost<Payout>("/commissions/payouts/", { amount, method });
}

export function approvePayout(id: string) {
  return apiPost<Payout>(`/commissions/payouts/${id}/approve/`);
}

export function rejectPayout(id: string) {
  return apiPost<Payout>(`/commissions/payouts/${id}/reject/`);
}

export function releaseWalletFunds() {
  return apiPost<{ released: number }>("/commissions/wallet/release/");
}
