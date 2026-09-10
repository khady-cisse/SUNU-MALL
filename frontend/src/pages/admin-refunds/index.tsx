import { useState, useCallback } from "react";
import { useAsync } from "@/hooks/useAsync";
import { listRefunds } from "@/api/payments";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Card, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { FilterBar, type FilterOption } from "@/components/ui/FilterBar";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { formatPrice, formatDate } from "@/lib/utils";

const PAGE_SIZE = 20;

const STATUS_FILTERS: FilterOption[] = [
  { value: "", label: "Tous" },
  { value: "pending", label: "En attente" },
  { value: "approved", label: "Approuvé" },
  { value: "rejected", label: "Rejeté" },
  { value: "completed", label: "Complété" },
];

export default function AdminRefundsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");

  const fetcher = useCallback(
    () => listRefunds({ page, status: status || undefined }),
    [page, status],
  );
  const { data, loading, error, refetch } = useAsync(fetcher, [page, status]);

  const refunds = data?.results ?? [];
  const totalPages = data ? Math.ceil(data.count / PAGE_SIZE) : 0;

  const columns: Column<Record<string, unknown>>[] = [
    { key: "order_id", label: "Commande", render: (row) => <span className="font-mono text-xs">{(row.order_id as string)?.slice(0, 8)}...</span> },
    { key: "customer_email", label: "Client", render: (row) => row.customer_email as string },
    { key: "store_name", label: "Boutique", render: (row) => row.store_name as string },
    { key: "amount", label: "Montant", render: (row) => formatPrice(row.amount as string) },
    { key: "reason", label: "Motif", render: (row) => <span className="truncate max-w-[200px] block">{row.reason as string}</span> },
    { key: "status", label: "Statut", render: (row) => <StatusBadge status={row.status as string} /> },
    { key: "created_at", label: "Date", render: (row) => formatDate(row.created_at as string) },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Remboursements" }]} />
      <Card>
        <CardTitle>Remboursements</CardTitle>
        <FilterBar
          className="mt-4"
          filters={[{ key: "status", label: "Statut", options: STATUS_FILTERS, value: status }]}
          onChange={(k, v) => { if (k === "status") { setStatus(v); setPage(1); } }}
          onReset={() => { setStatus(""); setPage(1); }}
        />
        <div className="mt-4">
          <DataTable
            columns={columns}
            data={refunds as unknown as Record<string, unknown>[]}
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
