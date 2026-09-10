import { apiGet, apiPost } from "@/lib/api";
import type { Paginated, SupportTicket, TicketMessage } from "@/types";

export async function listTickets(params?: { page?: number; page_size?: number }) {
  const qs = new URLSearchParams();
  if (params?.page) qs.set("page", String(params.page));
  if (params?.page_size) qs.set("page_size", String(params.page_size));
  const query = qs.toString();
  return apiGet<Paginated<SupportTicket>>(`/complaints/tickets/${query ? `?${query}` : ""}`);
}

export function createTicket(payload: {
  category: string;
  subject: string;
  description: string;
}) {
  return apiPost<SupportTicket>("/complaints/tickets/", payload);
}

export function replyToTicket(id: string, body: string) {
  return apiPost<TicketMessage>(`/complaints/tickets/${id}/reply/`, { body });
}

export function closeTicket(id: string) {
  return apiPost<SupportTicket>(`/complaints/tickets/${id}/close/`);
}