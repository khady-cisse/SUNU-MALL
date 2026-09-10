import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { apiGet } from "@/lib/api";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Card, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { FilterBar, type FilterOption } from "@/components/ui/FilterBar";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { formatDate } from "@/lib/utils";
import type { Paginated } from "@/types";

const PAGE_SIZE = 20;

interface Complaint {
  id: string;
  reference: string;
  complainant_name: string;
  category: string;
  priority: string;
  status: string;
  assignee_name: string | null;
  store_name: string | null;
  order_id: string | null;
  created_at: string;
}

const STATUS_FILTERS: FilterOption[] = [
  { value: "", label: "Tous" },
  { value: "open", label: "Ouvert" },
  { value: "assigned", label: "Assigné" },
  { value: "in_progress", label: "En cours" },
  { value: "escalated", label: "Escaladé" },
  { value: "resolved", label: "Résolu" },
  { value: "closed", label: "Fermé" },
];

const PRIORITY_FILTERS: FilterOption[] = [
  { value: "", label: "Toutes" },
  { value: "low", label: "Basse" },
  { value: "medium", label: "Moyenne" },
  { value: "high", label: "Haute" },
  { value: "critical", label: "Critique" },
];

const CATEGORY_MAP: Record<string, string> = {
  order_not_received: "Produit non reçu",
  wrong_item: "Mauvais produit",
  defective_product: "Produit défectueux",
  late_delivery: "Retard livraison",
  seller_behavior: "Problème vendeur",
  driver_behavior: "Problème livreur",
  incorrect_charge: "Paiement",
  refund_issue: "Remboursement",
  quality_issue: "Qualité",
  other: "Autre",
};

export default function AdminComplaintsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const navigate = useNavigate();

  const fetcher = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (status) params.set("status", status);
    if (priority) params.set("priority", priority);
    return apiGet<Paginated<Complaint>>(`/complaints/complaints/?${params.toString()}`);
  }, [page, status, priority]);
  const { data, loading, error, refetch } = useAsync(fetcher, [page, status, priority]);

  const complaints = data?.results ?? [];
  const totalPages = data ? Math.ceil(data.count / PAGE_SIZE) : 0;

  const columns: Column<Record<string, unknown>>[] = [
    { key: "reference", label: "Référence", render: (row) => <span className="font-mono text-xs font-medium">{row.reference as string}</span> },
    { key: "complainant_name", label: "Plaignant", render: (row) => row.complainant_name as string },
    { key: "category", label: "Catégorie", render: (row) => CATEGORY_MAP[row.category as string] ?? row.category as string },
    { key: "priority", label: "Priorité", render: (row) => <StatusBadge status={row.priority as string} /> },
    { key: "status", label: "Statut", render: (row) => <StatusBadge status={row.status as string} /> },
    { key: "assignee_name", label: "Assigné à", render: (row) => (row.assignee_name as string) ?? "Non assigné" },
    { key: "created_at", label: "Date", render: (row) => formatDate(row.created_at as string) },
    {
      key: "actions", label: "",
      render: (row) => (
        <button onClick={() => navigate(`/admin-complaints/${row.id}`)} className="text-orange-600 hover:underline text-xs">
          Voir <ArrowRight className="inline h-3 w-3" />
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Plaintes & Litiges" }]} />
      <Card>
        <CardTitle>Plaintes & Litiges</CardTitle>
        <FilterBar
          className="mt-4"
          filters={[
            { key: "status", label: "Statut", options: STATUS_FILTERS, value: status },
            { key: "priority", label: "Priorité", options: PRIORITY_FILTERS, value: priority },
          ]}
          onChange={(k, v) => {
            if (k === "status") setStatus(v);
            if (k === "priority") setPriority(v);
            setPage(1);
          }}
          onReset={() => { setStatus(""); setPriority(""); setPage(1); }}
        />
        <div className="mt-4">
          <DataTable
            columns={columns}
            data={complaints as unknown as Record<string, unknown>[]}
            loading={loading}
            error={error}
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            onRetry={refetch}
            totalItems={data?.count}
            pageSize={PAGE_SIZE}
            keyExtractor={(row) => row.id as string}
            onRowClick={(row) => navigate(`/admin-complaints/${row.id}`)}
          />
        </div>
      </Card>
    </div>
  );
}
