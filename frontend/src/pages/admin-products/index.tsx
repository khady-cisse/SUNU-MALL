import { useState, useCallback } from "react";
import { Package } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { searchProducts } from "@/api/catalog";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Card, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { FilterBar, type FilterOption } from "@/components/ui/FilterBar";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { formatPrice, formatDate } from "@/lib/utils";

const PAGE_SIZE = 20;

const STATUS_FILTERS: FilterOption[] = [
  { value: "", label: "Tous" },
  { value: "active", label: "Actif" },
  { value: "inactive", label: "Inactif" },
  { value: "draft", label: "Brouillon" },
];

export default function AdminProductsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [sortField, setSortField] = useState<string>("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc" | null>("desc");

  const fetcher = useCallback(
    () => searchProducts({ status: status || undefined, page } as any),
    [page, status],
  );
  const { data, loading, error, refetch } = useAsync(fetcher, [page, status]);

  const handleSort = (key: string) => {
    if (sortField === key) setSortDir((d) => (d === "asc" ? "desc" : d === "desc" ? null : "asc"));
    else { setSortField(key); setSortDir("asc"); }
  };

  const products = data?.results ?? [];
  const totalPages = data ? Math.ceil(data.count / PAGE_SIZE) : 0;

  const columns: Column<Record<string, unknown>>[] = [
    {
      key: "name", label: "Produit", sortable: true,
      render: (row) => (
        <div className="flex items-center gap-3">
          {(() => { const imgs = row.images as { url: string }[] | undefined; return imgs?.[0]?.url; })() ? (
            <img src={(() => { const imgs = row.images as { url: string }[] | undefined; return imgs?.[0]?.url; })()} alt="" className="h-10 w-10 rounded object-cover" />
          ) : (
            <div className="grid h-10 w-10 place-items-center rounded bg-muted"><Package className="h-5 w-5 text-muted-foreground" /></div>
          )}
          <div>
            <p className="font-medium text-ink">{row.name as string}</p>
            <p className="text-xs text-muted-foreground">{row.store_name as string}</p>
          </div>
        </div>
      ),
    },
    { key: "base_price", label: "Prix", sortable: true, render: (row) => formatPrice(row.base_price as string) },
    { key: "status", label: "Statut", sortable: true, render: (row) => <StatusBadge status={row.status as string} /> },
    { key: "sold_quantity", label: "Ventes", sortable: true, render: (row) => (row.sold_quantity as number) ?? 0 },
    { key: "created_at", label: "Créé le", sortable: true, render: (row) => formatDate(row.created_at as string) },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Produits" }]} />
      <Card>
        <CardTitle>Produits</CardTitle>
        <FilterBar
          className="mt-4"
          filters={[{ key: "status", label: "Statut", options: STATUS_FILTERS, value: status }]}
          onChange={(k, v) => { if (k === "status") { setStatus(v); setPage(1); } }}
          onReset={() => { setStatus(""); setPage(1); }}
        />
        <div className="mt-4">
          <DataTable
            columns={columns}
            data={products as unknown as Record<string, unknown>[]}
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
