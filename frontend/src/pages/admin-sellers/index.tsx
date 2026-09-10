import { useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { Store, ArrowRight } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { listStoresPaginated } from "@/api/catalog";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Card, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { FilterBar, type FilterOption } from "@/components/ui/FilterBar";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 20;

const STATUS_FILTERS: FilterOption[] = [
  { value: "", label: "Tous" },
  { value: "active", label: "Actif" },
  { value: "inactive", label: "Inactif" },
  { value: "suspended", label: "Suspendu" },
];

export default function AdminSellersPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [sortField, setSortField] = useState<string>("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc" | null>("desc");

  const fetcher = useCallback(
    () => listStoresPaginated({ status: status || undefined, page }),
    [page, status],
  );
  const { data, loading, error, refetch } = useAsync(fetcher, [page, status]);

  const handleSort = (key: string) => {
    if (sortField === key) {
      setSortDir((d) => (d === "asc" ? "desc" : d === "desc" ? null : "asc"));
    } else {
      setSortField(key);
      setSortDir("asc");
    }
  };

  const stores = data?.results ?? [];
  const totalPages = data ? Math.ceil(data.count / PAGE_SIZE) : 0;

  const columns: Column<Record<string, unknown>>[] = [
    {
      key: "name", label: "Boutique", sortable: true,
      render: (row) => (
        <div className="flex items-center gap-3">
          {row.logo_url ? (
            <img src={row.logo_url as string} alt="" className="h-8 w-8 rounded object-cover" />
          ) : (
            <div className="grid h-8 w-8 place-items-center rounded bg-muted"><Store className="h-4 w-4 text-muted-foreground" /></div>
          )}
          <div>
            <p className="font-medium text-ink">{row.name as string}</p>
            <p className="text-xs text-muted-foreground">{row.owner_email as string}</p>
          </div>
        </div>
      ),
    },
    { key: "status", label: "Statut", sortable: true, render: (row) => <StatusBadge status={row.status as string} /> },
    { key: "category_names", label: "Catégories", render: (row) => (row.category_names as string[])?.join(", ") || "—" },
    { key: "review_count", label: "Avis", sortable: true, render: (row) => row.rating ? `${row.rating}/5 (${row.review_count})` : "—" },
    { key: "created_at", label: "Créé le", sortable: true, render: (row) => formatDate(row.created_at as string) },
    {
      key: "actions", label: "",
      render: (row) => (
        <Link to={`/admin-sellers?highlight=${row.id}`} className="text-orange-600 hover:underline text-xs">
          Voir détails <ArrowRight className="inline h-3 w-3" />
        </Link>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Vendeurs" }]} />
      <Card>
        <CardTitle>Vendeurs & Boutiques</CardTitle>
        <FilterBar
          className="mt-4"
          filters={[{ key: "status", label: "Statut", options: STATUS_FILTERS, value: status }]}
          onChange={(k, v) => { if (k === "status") { setStatus(v); setPage(1); } }}
          onReset={() => { setStatus(""); setPage(1); }}
        />
        <div className="mt-4">
          <DataTable
            columns={columns}
            data={stores as unknown as Record<string, unknown>[]}
            loading={loading}
            error={error}
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            sortField={sortField}
            sortDir={sortDir}
            onSort={handleSort}
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
