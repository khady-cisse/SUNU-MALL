import { useState, useCallback } from "react";
import { useAsync } from "@/hooks/useAsync";
import { apiGet } from "@/lib/api";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Card, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { FilterBar, type FilterOption } from "@/components/ui/FilterBar";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { formatDate } from "@/lib/utils";
import type { Paginated, Delivery } from "@/types";

const PAGE_SIZE = 20;

const STATUS_FILTERS: FilterOption[] = [
  { value: "", label: "Tous" },
  { value: "pending", label: "En attente" },
  { value: "assigned", label: "Assigné" },
  { value: "picked_up", label: "Enlevé" },
  { value: "delivered", label: "Livré" },
  { value: "cancelled", label: "Annulé" },
];

export default function AdminDeliveriesPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");

  const fetcher = useCallback(
    () => apiGet<Paginated<Delivery>>(`/orders/deliveries/?page=${page}&page_size=${PAGE_SIZE}${status ? `&status=${status}` : ""}`),
    [page, status],
  );
  const { data, loading, error, refetch } = useAsync(fetcher, [page, status]);

  const deliveries = data?.results ?? [];
  const totalPages = data ? Math.ceil(data.count / PAGE_SIZE) : 0;

  const columns: Column<Record<string, unknown>>[] = [
    { key: "id", label: "Livraison", render: (row) => <span className="font-mono text-xs">{(row.id as string).slice(0, 8)}...</span> },
    { key: "order", label: "Commande", render: (row) => <span className="font-mono text-xs">{(row.order as string).slice(0, 8)}...</span> },
    { key: "driver_detail", label: "Livreur", render: (row) => {
      const d = row.driver_detail as { full_name: string } | null;
      return d ? d.full_name : "Non assigné";
    }},
    { key: "status", label: "Statut", render: (row) => <StatusBadge status={row.status as string} /> },
    { key: "picked_up_at", label: "Enlevé le", render: (row) => row.picked_up_at ? formatDate(row.picked_up_at as string) : "—" },
    { key: "delivered_at", label: "Livré le", render: (row) => row.delivered_at ? formatDate(row.delivered_at as string) : "—" },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Livraisons" }]} />
      <Card>
        <CardTitle>Livraisons</CardTitle>
        <FilterBar
          className="mt-4"
          filters={[{ key: "status", label: "Statut", options: STATUS_FILTERS, value: status }]}
          onChange={(k, v) => { if (k === "status") { setStatus(v); setPage(1); } }}
          onReset={() => { setStatus(""); setPage(1); }}
        />
        <div className="mt-4">
          <DataTable
            columns={columns}
            data={deliveries as unknown as Record<string, unknown>[]}
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
