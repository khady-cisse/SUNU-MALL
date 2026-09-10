import { useState, useCallback } from "react";
import { Lock, ShieldCheck } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { listAuditLogs, listSecurityLogs } from "@/api/security";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Card, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 50;

export default function AdminSecurityPage() {
  const [tab, setTab] = useState<"audit" | "security">("audit");
  const [page, setPage] = useState(1);

  const auditFetcher = useCallback(() => listAuditLogs({ page }), [page]);
  const securityFetcher = useCallback(() => listSecurityLogs({ page }), [page]);

  const auditData = useAsync(auditFetcher, [page]);
  const securityData = useAsync(securityFetcher, [page]);

  const currentData = tab === "audit" ? auditData : securityData;
  const { data, loading, error, refetch } = currentData;

  const logs = data?.results ?? [];
  const totalPages = data ? Math.ceil(data.count / PAGE_SIZE) : 0;

  const auditColumns: Column<Record<string, unknown>>[] = [
    { key: "admin_name", label: "Admin", render: (row) => row.admin_name as string ?? "—" },
    { key: "action", label: "Action", render: (row) => <StatusBadge status={row.action as string} /> },
    { key: "object_type", label: "Ressource", render: (row) => <span className="font-mono text-xs">{row.object_type as string}</span> },
    { key: "object_id", label: "ID", render: (row) => <span className="font-mono text-xs truncate block max-w-[120px]">{row.object_id as string}</span> },
    { key: "summary", label: "Résumé", render: (row) => <span className="truncate block max-w-[250px]">{row.summary as string}</span> },
    { key: "ip_address", label: "IP", render: (row) => row.ip_address as string ?? "—" },
    { key: "created_at", label: "Date", render: (row) => formatDate(row.created_at as string) },
  ];

  const securityColumns: Column<Record<string, unknown>>[] = [
    { key: "user_name", label: "Utilisateur", render: (row) => row.user_name as string ?? "—" },
    { key: "action", label: "Action", render: (row) => <StatusBadge status={row.action as string} /> },
    { key: "ip_address", label: "IP", render: (row) => row.ip_address as string ?? "—" },
    { key: "user_agent", label: "Navigateur", render: (row) => <span className="truncate block max-w-[200px] text-xs">{row.user_agent as string}</span> },
    { key: "created_at", label: "Date", render: (row) => formatDate(row.created_at as string) },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Sécurité & Audit" }]} />

      <div className="flex gap-2">
        <button
          onClick={() => { setTab("audit"); setPage(1); }}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${tab === "audit" ? "bg-orange-50 text-orange-700" : "text-muted-foreground hover:bg-muted"}`}
        >
          <ShieldCheck className="h-4 w-4" /> Journal d'audit
        </button>
        <button
          onClick={() => { setTab("security"); setPage(1); }}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${tab === "security" ? "bg-orange-50 text-orange-700" : "text-muted-foreground hover:bg-muted"}`}
        >
          <Lock className="h-4 w-4" /> Logs de sécurité
        </button>
      </div>

      <Card>
        <CardTitle>{tab === "audit" ? "Journal d'audit admin" : "Journal de sécurité"}</CardTitle>
        <div className="mt-4">
          <DataTable
            columns={tab === "audit" ? auditColumns : securityColumns}
            data={logs as unknown as Record<string, unknown>[]}
            loading={loading}
            error={error}
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            onRetry={refetch}
            totalItems={data?.count}
            pageSize={PAGE_SIZE}
            keyExtractor={(row) => String(row.id)}
          />
        </div>
      </Card>
    </div>
  );
}
