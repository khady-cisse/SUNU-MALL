import { Badge } from "./Badge";

type StatusConfig = {
  label: string;
  variant: "default" | "success" | "warning" | "danger" | "sponsored";
};

const STATUS_MAP: Record<string, StatusConfig> = {
  active: { label: "Actif", variant: "success" },
  inactive: { label: "Inactif", variant: "default" },
  suspended: { label: "Suspendu", variant: "danger" },
  blocked: { label: "Bloqué", variant: "danger" },
  pending: { label: "En attente", variant: "warning" },
  success: { label: "Succès", variant: "success" },
  failed: { label: "Échoué", variant: "danger" },
  refunded: { label: "Remboursé", variant: "default" },
  approved: { label: "Approuvé", variant: "success" },
  rejected: { label: "Rejeté", variant: "danger" },
  completed: { label: "Complété", variant: "success" },
  open: { label: "Ouvert", variant: "warning" },
  assigned: { label: "Assigné", variant: "default" },
  in_progress: { label: "En cours", variant: "warning" },
  escalated: { label: "Escaladé", variant: "danger" },
  resolved: { label: "Résolu", variant: "success" },
  closed: { label: "Fermé", variant: "default" },
  investigating: { label: "En cours", variant: "warning" },
  identified: { label: "Identifié", variant: "warning" },
  mitigating: { label: "Mitigation", variant: "warning" },
  draft: { label: "Brouillon", variant: "default" },
  cancelled: { label: "Annulé", variant: "danger" },
  processing: { label: "En cours", variant: "warning" },
  shipped: { label: "Expédié", variant: "default" },
  delivered: { label: "Livré", variant: "success" },
  paid: { label: "Payé", variant: "success" },
  available: { label: "Disponible", variant: "success" },
  busy: { label: "En course", variant: "warning" },
  offline: { label: "Hors ligne", variant: "default" },
  PENDING: { label: "En attente", variant: "warning" },
  SUBMITTED: { label: "Soumis", variant: "default" },
  UNDER_REVIEW: { label: "En examen", variant: "warning" },
  VERIFIED: { label: "Vérifié", variant: "success" },
  REJECTED: { label: "Rejeté", variant: "danger" },
  SUSPENDED: { label: "Suspendu", variant: "danger" },
  BLOCKED: { label: "Bloqué", variant: "danger" },
  INFO: { label: "Info", variant: "default" },
  WARNING: { label: "Attention", variant: "warning" },
  CRITICAL: { label: "Critique", variant: "danger" },
  EMERGENCY: { label: "Urgence", variant: "danger" },
  low: { label: "Basse", variant: "default" },
  medium: { label: "Moyenne", variant: "warning" },
  high: { label: "Haute", variant: "warning" },
  critical: { label: "Critique", variant: "danger" },
};

const FALLBACK: StatusConfig = { label: "—", variant: "default" };

interface StatusBadgeProps {
  status: string;
  customMap?: Record<string, StatusConfig>;
}

export function StatusBadge({ status, customMap }: StatusBadgeProps) {
  const cfg = customMap?.[status] ?? STATUS_MAP[status] ?? FALLBACK;
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}
