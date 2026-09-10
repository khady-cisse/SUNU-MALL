import { useState, useCallback } from "react";
import { Banknote } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { apiGet } from "@/lib/api";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Card, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { StatCard } from "@/components/ui/StatCard";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { formatDate } from "@/lib/utils";
import type { Paginated, Subscription } from "@/types";

const PAGE_SIZE = 20;

export default function AdminSubscriptionsPage() {
  const [page, setPage] = useState(1);

  const fetcher = useCallback(
    () => apiGet<Paginated<Subscription>>(`/monetization/subscriptions/?page=${page}&page_size=${PAGE_SIZE}`),
    [page],
  );
  const { data, loading, error, refetch } = useAsync(fetcher, [page]);

  const subs = data?.results ?? [];
  const totalPages = data ? Math.ceil(data.count / PAGE_SIZE) : 0;

  const activeCount = subs.filter((s) => s.status === "active").length;
  const expiredCount = subs.filter((s) => s.status === "expired").length;

  const columns: Column<Record<string, unknown>>[] = [
    { key: "plan_name", label: "Plan", render: (row) => <span className="font-medium">{row.plan_name as string}</span> },
    { key: "status", label: "Statut", render: (row) => <StatusBadge status={row.status as string} /> },
    { key: "subscriber_type", label: "Type", render: (row) => row.subscriber_type as string },
    { key: "starts_at", label: "Début", render: (row) => formatDate(row.starts_at as string) },
    { key: "ends_at", label: "Fin", render: (row) => row.ends_at ? formatDate(row.ends_at as string) : "—" },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Abonnements" }]} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total" value={data?.count ?? 0} icon={<Banknote className="h-5 w-5" />} tone="orange" />
        <StatCard label="Actifs" value={activeCount} tone="green" />
        <StatCard label="Expirés" value={expiredCount} tone="red" />
        <StatCard label="Plans" value="3" subtitle="STARTER / PRO / BUSINESS" tone="blue" />
      </div>

      <Card>
        <CardTitle>Abonnements</CardTitle>
        <div className="mt-4">
          <DataTable
            columns={columns}
            data={subs as unknown as Record<string, unknown>[]}
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
