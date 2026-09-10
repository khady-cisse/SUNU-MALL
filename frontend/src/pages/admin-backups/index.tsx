import { useState, useCallback } from "react";
import { Plus } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { listBackups, createBackup } from "@/api/ops";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 20;

function formatBytes(bytes: number) {
  if (bytes === 0) return "0 o";
  const k = 1024;
  const sizes = ["o", "Ko", "Mo", "Go"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

export default function AdminBackupsPage() {
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);

  const fetcher = useCallback(() => listBackups({ page }), [page]);
  const { data, loading, error, refetch } = useAsync(fetcher, [page]);

  const backups = data?.results ?? [];
  const totalPages = data ? Math.ceil(data.count / PAGE_SIZE) : 0;

  const handleCreateBackup = async () => {
    setCreating(true);
    try {
      await createBackup();
      refetch();
    } catch { /* handled */ }
    setCreating(false);
  };

  const columns: Column<Record<string, unknown>>[] = [
    { key: "backup_type", label: "Type", render: (row) => <span className="font-medium">{row.backup_type as string}</span> },
    { key: "status", label: "Statut", render: (row) => <StatusBadge status={row.status as string} /> },
    { key: "file_size_bytes", label: "Taille", render: (row) => formatBytes(row.file_size_bytes as number) },
    { key: "started_at", label: "Début", render: (row) => formatDate(row.started_at as string) },
    { key: "completed_at", label: "Fin", render: (row) => row.completed_at ? formatDate(row.completed_at as string) : "—" },
    { key: "error_message", label: "Erreur", render: (row) => row.error_message ? <span className="text-red-600 text-xs">{row.error_message as string}</span> : "—" },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Backups" }]} />

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-ink">Sauvegardes</h1>
        <Button onClick={handleCreateBackup} loading={creating}><Plus className="h-4 w-4" /> Nouvelle sauvegarde</Button>
      </div>

      <Card>
        <CardTitle>Historique des sauvegardes</CardTitle>
        <div className="mt-4">
          <DataTable
            columns={columns}
            data={backups as unknown as Record<string, unknown>[]}
            loading={loading}
            error={error}
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            onRetry={refetch}
            totalItems={data?.count}
            pageSize={PAGE_SIZE}
            keyExtractor={(row) => row.id as string}
          />
        </div>
      </Card>
    </div>
  );
}
