import { apiGet } from "@/lib/api";
import type { Paginated } from "@/types";

export interface SecurityLog {
  id: number;
  user: string;
  user_name: string;
  action: string;
  ip_address: string | null;
  user_agent: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AdminAuditLog {
  id: number;
  admin: string;
  admin_name: string;
  action: string;
  object_type: string;
  object_id: string;
  summary: string;
  changes: Record<string, unknown>;
  ip_address: string | null;
  user_agent: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export async function listSecurityLogs(params?: { page?: number; action?: string; user?: string }) {
  const p = new URLSearchParams();
  if (params?.page) p.set("page", String(params.page));
  if (params?.action) p.set("action", params.action);
  if (params?.user) p.set("user", params.user);
  return apiGet<Paginated<SecurityLog>>(`/security/logs/?${p.toString()}`);
}

export async function listAuditLogs(params?: { page?: number; action?: string; admin?: string; object_type?: string }) {
  const p = new URLSearchParams();
  if (params?.page) p.set("page", String(params.page));
  if (params?.action) p.set("action", params.action);
  if (params?.admin) p.set("admin", params.admin);
  if (params?.object_type) p.set("object_type", params.object_type);
  return apiGet<Paginated<AdminAuditLog>>(`/security/audit-logs/?${p.toString()}`);
}
