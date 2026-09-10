import { useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useAsync } from "@/hooks/useAsync";
import { apiGet, apiPost } from "@/lib/api";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Badge } from "@/components/ui/Badge";
import { Timeline, type TimelineEntry } from "@/components/ui/Timeline";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { formatDate } from "@/lib/utils";

interface ComplaintDetail {
  id: string;
  reference: string;
  complainant: string;
  complainant_name: string;
  complainant_email: string;
  order: string | null;
  store: string | null;
  store_name: string | null;
  delivery: string | null;
  driver: string | null;
  driver_name: string | null;
  payment: string | null;
  category: string;
  description: string;
  priority: string;
  status: string;
  assignee: string | null;
  assignee_name: string | null;
  resolution_decision: string | null;
  resolution_note: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  timeline: { action: string; actor_name: string; actor_role: string; note: string; created_at: string }[];
  created_at: string;
}

export default function AdminComplaintDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [confirmAction, setConfirmAction] = useState<string | null>(null);

  const fetcher = useCallback(() => apiGet<ComplaintDetail>(`/complaints/complaints/${id}/`), [id]);
  const { data: complaint, loading, error, refetch } = useAsync(fetcher, [id]);

  const handleAction = async (action: string) => {
    try {
      await apiPost(`/complaints/complaints/${id}/${action}/`, {});
      refetch();
    } catch {
      // error handled by UI
    }
    setConfirmAction(null);
  };

  if (loading) return <Spinner label="Chargement de la plainte..." />;
  if (error) return <ErrorState message={error.message} onRetry={refetch} />;
  if (!complaint) return <ErrorState message="Plainte introuvable" />;

  const timelineEntries: TimelineEntry[] = (complaint.timeline ?? []).map((e) => ({
    date: e.created_at,
    actor: e.actor_name,
    actorRole: e.actor_role,
    action: e.action,
    detail: e.note,
  }));

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { label: "Dashboard", to: "/admin" },
          { label: "Plaintes", to: "/admin-complaints" },
          { label: complaint.reference },
        ]}
      />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-ink">{complaint.reference}</h1>
          <div className="mt-2 flex flex-wrap gap-2">
            <StatusBadge status={complaint.status} />
            <StatusBadge status={complaint.priority} />
            <Badge>{complaint.category}</Badge>
          </div>
        </div>
        <div className="flex gap-2">
          {complaint.status === "open" && (
            <Button size="sm" onClick={() => setConfirmAction("resolve")}>Résoudre</Button>
          )}
          {complaint.status !== "closed" && complaint.status !== "resolved" && (
            <Button size="sm" variant="secondary" onClick={() => setConfirmAction("close")}>Fermer</Button>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardTitle>Description</CardTitle>
            <p className="mt-2 text-sm text-muted-foreground whitespace-pre-wrap">{complaint.description}</p>
          </Card>

          <Card>
            <CardTitle>Timeline</CardTitle>
            <div className="mt-4">
              <Timeline entries={timelineEntries} />
            </div>
          </Card>

          {complaint.resolution_decision && (
            <Card>
              <CardTitle>Décision</CardTitle>
              <div className="mt-2 space-y-1">
                <p className="text-sm"><span className="font-medium">Décision :</span> {complaint.resolution_decision}</p>
                {complaint.resolution_note && <p className="text-sm text-muted-foreground">{complaint.resolution_note}</p>}
                {complaint.resolved_at && <p className="text-xs text-muted-foreground">Résolu le {formatDate(complaint.resolved_at)}</p>}
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card>
            <CardTitle>Informations</CardTitle>
            <div className="mt-3 space-y-3 text-sm">
              <div>
                <p className="text-muted-foreground">Plaignant</p>
                <p className="font-medium">{complaint.complainant_name}</p>
                <p className="text-xs text-muted-foreground">{complaint.complainant_email}</p>
              </div>
              {complaint.assignee_name && (
                <div>
                  <p className="text-muted-foreground">Assigné à</p>
                  <p className="font-medium">{complaint.assignee_name}</p>
                </div>
              )}
              {complaint.store_name && (
                <div>
                  <p className="text-muted-foreground">Boutique</p>
                  <p className="font-medium">{complaint.store_name}</p>
                </div>
              )}
              {complaint.driver_name && (
                <div>
                  <p className="text-muted-foreground">Livreur</p>
                  <p className="font-medium">{complaint.driver_name}</p>
                </div>
              )}
              <div>
                <p className="text-muted-foreground">Créé le</p>
                <p>{formatDate(complaint.created_at)}</p>
              </div>
            </div>
          </Card>
        </div>
      </div>

      <ConfirmDialog
        open={confirmAction === "resolve"}
        onClose={() => setConfirmAction(null)}
        onConfirm={() => handleAction("resolve")}
        title="Résoudre la plainte"
        message="Êtes-vous sûr de vouloir marquer cette plainte comme résolue ?"
        confirmLabel="Résoudre"
      />
      <ConfirmDialog
        open={confirmAction === "close"}
        onClose={() => setConfirmAction(null)}
        onConfirm={() => handleAction("close")}
        title="Fermer la plainte"
        message="Êtes-vous sûr de vouloir fermer cette plainte ?"
        confirmLabel="Fermer"
      />
    </div>
  );
}
