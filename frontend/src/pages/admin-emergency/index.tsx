import { useState, useCallback } from "react";
import { Zap, ShieldAlert } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { getHealth, listEmergencySessions, createEmergencySession, revokeEmergencySession, listIncidents, listBackups } from "@/api/ops";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { StatCard } from "@/components/ui/StatCard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { formatDate, cn } from "@/lib/utils";

export default function AdminEmergencyPage() {
  const healthFetcher = useCallback(() => getHealth(), []);
  const sessionsFetcher = useCallback(() => listEmergencySessions(), []);
  const incidentsFetcher = useCallback(() => listIncidents({ status: "open" }), []);
  const backupsFetcher = useCallback(() => listBackups({}), []);

  const { data: health, loading: healthLoading } = useAsync(healthFetcher, []);
  const { data: sessions, loading: sessionsLoading, refetch: refetchSessions } = useAsync(sessionsFetcher, []);
  const { data: incidents, loading: incidentsLoading } = useAsync(incidentsFetcher, []);
  const { data: backups, loading: backupsLoading } = useAsync(backupsFetcher, []);

  const [showEmergency, setShowEmergency] = useState(false);
  const [reason, setReason] = useState("");
  const [creating, setCreating] = useState(false);
  const [revokeId, setRevokeId] = useState<string | null>(null);

  const handleCreateEmergency = async () => {
    setCreating(true);
    try {
      await createEmergencySession({ reason, scopes: ["full"] });
      setShowEmergency(false);
      setReason("");
      refetchSessions();
    } catch { /* handled */ }
    setCreating(false);
  };

  const handleRevoke = async () => {
    if (!revokeId) return;
    try {
      await revokeEmergencySession(revokeId);
      refetchSessions();
    } catch { /* handled */ }
    setRevokeId(null);
  };

  const loading = healthLoading || sessionsLoading || incidentsLoading || backupsLoading;
  if (loading) return <Spinner label="Chargement du centre d'urgence..." />;

  const activeSessions = sessions?.results?.filter((s) => s.is_active) ?? [];
  const openIncidents = incidents?.results ?? [];
  const latestBackup = backups?.results?.[0];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Emergency Recovery" }]} />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Zap className="h-6 w-6 text-red-600" />
          <h1 className="text-xl font-bold text-ink">Emergency Recovery</h1>
        </div>
        <Button variant="danger" onClick={() => setShowEmergency(true)}>
          <ShieldAlert className="h-4 w-4" /> Accès d'urgence
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Services"
          value={health?.status === "ok" ? "Opérationnel" : "Dégradé"}
          tone={health?.status === "ok" ? "green" : "red"}
        />
        <StatCard
          label="Incidents ouverts"
          value={openIncidents.length}
          tone={openIncidents.length > 0 ? "red" : "green"}
        />
        <StatCard
          label="Sessions d'urgence"
          value={activeSessions.length}
          tone={activeSessions.length > 0 ? "red" : "green"}
        />
        <StatCard
          label="Dernière sauvegarde"
          value={latestBackup ? formatDate(latestBackup.started_at) : "Aucune"}
          tone={latestBackup?.status === "success" ? "green" : "orange"}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle>État des services</CardTitle>
          <div className="mt-3 space-y-2">
            {health?.checks && Object.entries(health.checks).map(([key, check]) => {
              const c = check as { status: string };
              return (
                <div key={key} className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
                  <span className="text-sm">{key}</span>
                  <span className={cn("h-2.5 w-2.5 rounded-full", c.status === "ok" ? "bg-green-500" : c.status === "degraded" ? "bg-amber-500" : "bg-red-500")} />
                </div>
              );
            })}
          </div>
        </Card>

        <Card>
          <CardTitle>Incidents ouverts</CardTitle>
          {openIncidents.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">Aucun incident ouvert.</p>
          ) : (
            <div className="mt-3 space-y-2">
              {openIncidents.map((inc: any) => (
                <div key={inc.id} className="rounded-lg border border-border px-3 py-2">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{inc.title}</span>
                    <StatusBadge status={inc.level} />
                  </div>
                  <p className="text-xs text-muted-foreground">{inc.service} — {inc.status}</p>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {activeSessions.length > 0 && (
        <Card>
          <CardTitle>Sessions d'urgence actives</CardTitle>
          <div className="mt-3 space-y-2">
            {activeSessions.map((s) => (
              <div key={s.id} className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-3 py-2">
                <div>
                  <p className="font-medium text-sm">{s.user_name}</p>
                  <p className="text-xs text-muted-foreground">Raison : {s.reason} — Expire : {formatDate(s.expires_at)}</p>
                </div>
                <Button size="sm" variant="danger" onClick={() => setRevokeId(s.id)}>Révoquer</Button>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Modal open={showEmergency} onClose={() => setShowEmergency(false)} title="Activer l'accès d'urgence" size="md">
        <p className="mb-4 text-sm text-muted-foreground">
          Cet accès accordera des permissions élevées de manière temporaire. Toute action sera journalisée.
        </p>
        <Input label="Raison" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Décrivez la raison de l'accès d'urgence..." />
        <div className="mt-4 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setShowEmergency(false)}>Annuler</Button>
          <Button variant="danger" loading={creating} disabled={!reason.trim()} onClick={handleCreateEmergency}>Activer</Button>
        </div>
      </Modal>

      <ConfirmDialog
        open={!!revokeId}
        onClose={() => setRevokeId(null)}
        onConfirm={handleRevoke}
        title="Révoquer l'accès d'urgence"
        message="L'accès d'urgence sera immédiatement révoqué."
        confirmLabel="Révoquer"
      />
    </div>
  );
}
