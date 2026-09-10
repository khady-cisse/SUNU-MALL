import { apiGet, apiPost, apiPatch } from "@/lib/api";
import type { Paginated } from "@/types";

export interface HealthStatus {
  status: "ok" | "degraded" | "down";
  checks: Record<string, { status: string; latency_ms?: number; detail?: string }>;
}

export interface Incident {
  id: string;
  reference: string;
  title: string;
  service: string;
  level: string;
  impact: string;
  status: string;
  description: string;
  assigned_to: string | null;
  assigned_to_name: string | null;
  root_cause: string;
  resolution: string;
  started_at: string;
  resolved_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface IncidentTimelineEntry {
  id: number;
  actor: string;
  actor_name: string;
  action: string;
  note: string;
  created_at: string;
}

export interface DeploymentVersion {
  id: string;
  version: string;
  commit_hash: string;
  environment: string;
  deployed_by: string;
  deployed_by_name: string;
  is_active: boolean;
  notes: string;
  deployed_at: string;
  created_at: string;
}

export interface BackupRecord {
  id: string;
  backup_type: string;
  status: string;
  file_path: string;
  file_size_bytes: number;
  started_at: string;
  completed_at: string | null;
  error_message: string;
  created_at: string;
}

export interface EmergencySession {
  id: string;
  user: string;
  user_name: string;
  scopes: string[];
  reason: string;
  is_active: boolean;
  expires_at: string;
  ip_address: string;
  created_at: string;
}

export interface SystemSetting {
  id: number;
  key: string;
  value: string;
  setting_type: string;
  description: string;
}

export interface AlertItem {
  title: string;
  count: number;
  severity: string;
  link: string;
}

export async function getHealth(): Promise<HealthStatus> {
  return apiGet<HealthStatus>("/health/");
}

export async function listIncidents(params?: { page?: number; status?: string }) {
  const p = new URLSearchParams();
  if (params?.page) p.set("page", String(params.page));
  if (params?.status) p.set("status", params.status);
  return apiGet<Paginated<Incident>>(`/ops/incidents/?${p.toString()}`);
}

export async function getIncident(id: string) {
  return apiGet<Incident>(`/ops/incidents/${id}/`);
}

export async function updateIncident(id: string, data: Partial<Incident>) {
  return apiPatch<Incident>(`/ops/incidents/${id}/`, data);
}

export async function createIncident(data: { title: string; service: string; level: string; impact: string; description: string }) {
  return apiPost<Incident>("/ops/incidents/", data);
}

export async function listVersions() {
  return apiGet<Paginated<DeploymentVersion>>("/ops/versions/");
}

export async function activateVersion(id: string) {
  return apiPost<DeploymentVersion>(`/ops/versions/${id}/activate/`);
}

export async function listBackups(params?: { page?: number }) {
  const p = new URLSearchParams();
  if (params?.page) p.set("page", String(params.page));
  return apiGet<Paginated<BackupRecord>>(`/ops/backups/?${p.toString()}`);
}

export async function createBackup() {
  return apiPost<BackupRecord>("/ops/backups/", {});
}

export async function listEmergencySessions() {
  return apiGet<Paginated<EmergencySession>>("/ops/emergency/");
}

export async function createEmergencySession(data: { reason: string; scopes: string[] }) {
  return apiPost<EmergencySession>("/ops/emergency/", data);
}

export async function revokeEmergencySession(id: string) {
  return apiPost<EmergencySession>(`/ops/emergency/${id}/revoke/`);
}

export async function getAlerts() {
  return apiGet<AlertItem[]>("/ops/alerts/");
}

export async function listSettings() {
  return apiGet<Paginated<SystemSetting>>("/ops/settings/");
}

export async function updateSetting(key: string, value: string) {
  return apiPost<SystemSetting>(`/ops/settings/set/`, { key, value });
}
