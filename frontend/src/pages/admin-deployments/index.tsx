import { useCallback } from "react";
import { useAsync } from "@/hooks/useAsync";
import { listVersions } from "@/api/ops";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Card, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { formatDate } from "@/lib/utils";

export default function AdminDeploymentsPage() {
  const fetcher = useCallback(() => listVersions(), []);
  const { data, loading, error, refetch } = useAsync(fetcher, []);

  const versions = data?.results ?? [];

  const columns: Column<Record<string, unknown>>[] = [
    {
      key: "version", label: "Version", render: (row) => (
        <div className="flex items-center gap-2">
          <span className="font-medium">{row.version as string}</span>
          {row.is_active as boolean && <Badge variant="success" size="sm">Active</Badge>}
        </div>
      ),
    },
    { key: "commit_hash", label: "Commit", render: (row) => <span className="font-mono text-xs">{(row.commit_hash as string)?.slice(0, 8)}</span> },
    { key: "environment", label: "Environnement" },
    { key: "deployed_by_name", label: "Déployé par" },
    { key: "deployed_at", label: "Date", render: (row) => formatDate(row.deployed_at as string) },
    { key: "notes", label: "Notes", render: (row) => <span className="truncate block max-w-[200px] text-muted-foreground">{String(row.notes ?? "")}</span> },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Déploiements" }]} />
      <Card>
        <CardTitle>Historique des déploiements</CardTitle>
        <div className="mt-4">
          <DataTable
            columns={columns}
            data={versions as unknown as Record<string, unknown>[]}
            loading={loading}
            error={error}
            onRetry={refetch}
            keyExtractor={(row) => row.id as string}
            emptyTitle="Aucun déploiement enregistré"
          />
        </div>
      </Card>
    </div>
  );
}
