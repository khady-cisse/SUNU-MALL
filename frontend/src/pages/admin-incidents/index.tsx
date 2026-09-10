import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { listIncidents, createIncident } from "@/api/ops";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { FilterBar, type FilterOption } from "@/components/ui/FilterBar";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 20;

const STATUS_FILTERS: FilterOption[] = [
  { value: "", label: "Tous" },
  { value: "open", label: "Ouvert" },
  { value: "investigating", label: "En cours" },
  { value: "identified", label: "Identifié" },
  { value: "mitigating", label: "Mitigation" },
  { value: "resolved", label: "Résolu" },
  { value: "closed", label: "Fermé" },
];

export default function AdminIncidentsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: "", service: "", level: "INFO", impact: "", description: "" });
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  const fetcher = useCallback(
    () => listIncidents({ page, status: status || undefined }),
    [page, status],
  );
  const { data, loading, error, refetch } = useAsync(fetcher, [page, status]);

  const incidents = data?.results ?? [];
  const totalPages = data ? Math.ceil(data.count / PAGE_SIZE) : 0;

  const handleCreate = async () => {
    setCreating(true);
    try {
      await createIncident(form);
      setShowCreate(false);
      setForm({ title: "", service: "", level: "INFO", impact: "", description: "" });
      refetch();
    } catch { /* handled */ }
    setCreating(false);
  };

  const columns: Column<Record<string, unknown>>[] = [
    { key: "reference", label: "Référence", render: (row) => <span className="font-mono text-xs font-medium">{row.reference as string}</span> },
    { key: "title", label: "Titre", render: (row) => <span className="font-medium">{row.title as string}</span> },
    { key: "service", label: "Service", render: (row) => row.service as string },
    { key: "level", label: "Niveau", render: (row) => <StatusBadge status={row.level as string} /> },
    { key: "status", label: "Statut", render: (row) => <StatusBadge status={row.status as string} /> },
    { key: "started_at", label: "Début", render: (row) => formatDate(row.started_at as string) },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Incidents" }]} />

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-ink">Incidents techniques</h1>
        <Button onClick={() => setShowCreate(true)}><Plus className="h-4 w-4" /> Nouvel incident</Button>
      </div>

      <Card>
        <FilterBar
          filters={[{ key: "status", label: "Statut", options: STATUS_FILTERS, value: status }]}
          onChange={(k, v) => { if (k === "status") { setStatus(v); setPage(1); } }}
          onReset={() => { setStatus(""); setPage(1); }}
        />
        <div className="mt-4">
          <DataTable
            columns={columns}
            data={incidents as unknown as Record<string, unknown>[]}
            loading={loading}
            error={error}
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            onRetry={refetch}
            totalItems={data?.count}
            pageSize={PAGE_SIZE}
            keyExtractor={(row) => row.id as string}
            onRowClick={(row) => navigate(`/admin-incidents/${row.id}`)}
          />
        </div>
      </Card>

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Nouvel incident" size="lg">
        <div className="space-y-4">
          <Input label="Titre" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <Input label="Service" value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value })} />
          <div>
            <label className="mb-1 block text-sm font-medium">Niveau</label>
            <select value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })} className="w-full rounded-lg border border-border px-3 py-2 text-sm">
              <option value="INFO">Info</option>
              <option value="WARNING">Warning</option>
              <option value="CRITICAL">Critical</option>
              <option value="EMERGENCY">Emergency</option>
            </select>
          </div>
          <Input label="Impact" value={form.impact} onChange={(e) => setForm({ ...form, impact: e.target.value })} />
          <div>
            <label className="mb-1 block text-sm font-medium">Description</label>
            <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={3} className="w-full rounded-lg border border-border px-3 py-2 text-sm" />
          </div>
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setShowCreate(false)}>Annuler</Button>
            <Button onClick={handleCreate} loading={creating}>Créer</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
