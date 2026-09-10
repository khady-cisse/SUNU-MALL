import { useCallback } from "react";
import { CheckCircle, XCircle, AlertTriangle } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { getHealth } from "@/api/ops";
import { Card, CardTitle } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { cn } from "@/lib/utils";

const SERVICE_LABELS: Record<string, string> = {
  database: "Base de données",
  redis: "Redis",
  celery: "Celery Worker",
  celery_beat: "Celery Beat",
  storage: "Stockage (MinIO)",
  payments: "Paiements",
  notifications: "Notifications",
};

export default function AdminMonitoringPage() {
  const fetcher = useCallback(() => getHealth(), []);
  const { data: health, loading, error, refetch } = useAsync(fetcher, []);

  if (loading) return <Spinner label="Vérification de la santé..." />;
  if (error) return <ErrorState message={error.message} onRetry={refetch} />;
  if (!health) return null;

  const statusColor = (s: string) => {
    if (s === "ok") return "green";
    if (s === "degraded") return "orange";
    return "red";
  };

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Monitoring" }]} />

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-ink">Monitoring</h1>
        <button onClick={refetch} className="text-sm text-orange-600 hover:underline">Actualiser</button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Statut global"
          value={health.status === "ok" ? "Opérationnel" : health.status === "degraded" ? "Dégradé" : "Indisponible"}
          icon={health.status === "ok" ? <CheckCircle className="h-5 w-5" /> : health.status === "degraded" ? <AlertTriangle className="h-5 w-5" /> : <XCircle className="h-5 w-5" />}
          tone={statusColor(health.status) as "green" | "orange" | "red"}
        />
      </div>

      <Card>
        <CardTitle>Services</CardTitle>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(health.checks ?? {}).map(([key, check]) => {
            const c = check as { status: string; latency_ms?: number; detail?: string };
            return (
              <div
                key={key}
                className={cn(
                  "flex items-center justify-between rounded-xl border p-4",
                  c.status === "ok" ? "border-green-200 bg-green-50" : c.status === "degraded" ? "border-amber-200 bg-amber-50" : "border-red-200 bg-red-50",
                )}
              >
                <div>
                  <p className="font-medium text-ink">{SERVICE_LABELS[key] ?? key}</p>
                  {c.latency_ms != null && <p className="text-xs text-muted-foreground">{c.latency_ms}ms</p>}
                  {c.detail && <p className="text-xs text-muted-foreground">{c.detail}</p>}
                </div>
                <span className={cn("h-3 w-3 rounded-full", c.status === "ok" ? "bg-green-500" : c.status === "degraded" ? "bg-amber-500" : "bg-red-500")} />
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
