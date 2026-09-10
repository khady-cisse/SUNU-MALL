import { useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useAsync } from "@/hooks/useAsync";
import { getIncident, updateIncident } from "@/api/ops";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { formatDate } from "@/lib/utils";

export default function AdminIncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [saving, setSaving] = useState(false);

  const fetcher = useCallback(() => getIncident(id!), [id]);
  const { data: incident, loading, error, refetch } = useAsync(fetcher, [id]);

  const handleAction = async (action: string, data?: Record<string, string>) => {
    setSaving(true);
    try {
      await updateIncident(id!, { status: action, ...data } as any);
      refetch();
    } catch { /* handled */ }
    setSaving(false);
  };

  if (loading) return <Spinner label="Chargement..." />;
  if (error) return <ErrorState message={error.message} onRetry={refetch} />;
  if (!incident) return <ErrorState message="Incident introuvable" />;

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { label: "Dashboard", to: "/admin" },
          { label: "Incidents", to: "/admin-incidents" },
          { label: incident.reference },
        ]}
      />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-ink">{incident.title}</h1>
          <div className="mt-2 flex flex-wrap gap-2">
            <span className="font-mono text-sm text-muted-foreground">{incident.reference}</span>
            <StatusBadge status={incident.level} />
            <StatusBadge status={incident.status} />
          </div>
        </div>
        <div className="flex gap-2">
          {incident.status === "open" && (
            <Button size="sm" loading={saving} onClick={() => handleAction("investigating")}>Investiguer</Button>
          )}
          {incident.status === "investigating" && (
            <Button size="sm" loading={saving} onClick={() => handleAction("identified")}>Identifié</Button>
          )}
          {incident.status === "identified" && (
            <Button size="sm" loading={saving} onClick={() => handleAction("mitigating")}>Mitiger</Button>
          )}
          {incident.status !== "resolved" && incident.status !== "closed" && (
            <Button size="sm" loading={saving} onClick={() => handleAction("resolved")}>Résoudre</Button>
          )}
          {incident.status === "resolved" && (
            <Button size="sm" variant="secondary" loading={saving} onClick={() => handleAction("closed")}>Fermer</Button>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardTitle>Description</CardTitle>
            <p className="mt-2 text-sm text-muted-foreground whitespace-pre-wrap">{incident.description || "Aucune description."}</p>
          </Card>
          {incident.root_cause && (
            <Card>
              <CardTitle>Cause racine</CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">{incident.root_cause}</p>
            </Card>
          )}
          {incident.resolution && (
            <Card>
              <CardTitle>Résolution</CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">{incident.resolution}</p>
            </Card>
          )}
        </div>
        <div className="space-y-6">
          <Card>
            <CardTitle>Détails</CardTitle>
            <div className="mt-3 space-y-3 text-sm">
              <div><p className="text-muted-foreground">Service</p><p className="font-medium">{incident.service}</p></div>
              <div><p className="text-muted-foreground">Impact</p><p>{incident.impact || "—"}</p></div>
              <div><p className="text-muted-foreground">Début</p><p>{formatDate(incident.started_at)}</p></div>
              {incident.resolved_at && <div><p className="text-muted-foreground">Résolu le</p><p>{formatDate(incident.resolved_at)}</p></div>}
              {incident.assigned_to_name && <div><p className="text-muted-foreground">Assigné à</p><p className="font-medium">{incident.assigned_to_name}</p></div>}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
