import { useState, useCallback } from "react";
import { useAsync } from "@/hooks/useAsync";
import { apiGet } from "@/lib/api";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Card, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { formatDate } from "@/lib/utils";
import type { Paginated } from "@/types";

const PAGE_SIZE = 20;

interface Ticket {
  id: string;
  reference: string;
  requester_name: string;
  category: string;
  priority: string;
  status: string;
  assigned_to_name: string | null;
  created_at: string;
}

export default function AdminSupportPage() {
  const [page, setPage] = useState(1);

  const fetcher = useCallback(
    () => apiGet<Paginated<Ticket>>(`/complaints/tickets/?page=${page}&page_size=${PAGE_SIZE}`),
    [page],
  );
  const { data, loading, error, refetch } = useAsync(fetcher, [page]);

  const tickets = data?.results ?? [];
  const totalPages = data ? Math.ceil(data.count / PAGE_SIZE) : 0;

  const columns: Column<Record<string, unknown>>[] = [
    { key: "reference", label: "Référence", render: (row) => <span className="font-mono text-xs font-medium">{row.reference as string}</span> },
    { key: "requester_name", label: "Demandeur", render: (row) => row.requester_name as string },
    { key: "category", label: "Catégorie", render: (row) => row.category as string },
    { key: "priority", label: "Priorité", render: (row) => <StatusBadge status={row.priority as string} /> },
    { key: "status", label: "Statut", render: (row) => <StatusBadge status={row.status as string} /> },
    { key: "assigned_to_name", label: "Assigné à", render: (row) => (row.assigned_to_name as string) ?? "—" },
    { key: "created_at", label: "Date", render: (row) => formatDate(row.created_at as string) },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Tickets support" }]} />
      <Card>
        <CardTitle>Tickets support</CardTitle>
        <div className="mt-4">
          <DataTable
            columns={columns}
            data={tickets as unknown as Record<string, unknown>[]}
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
