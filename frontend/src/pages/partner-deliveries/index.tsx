import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, MapPin, PackageSearch } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as partnerApi from "@/api/partner";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { FilterBar } from "@/components/ui/FilterBar";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { DELIVERY_STATUS_LABEL, DELIVERY_STATUS_VARIANT } from "@/lib/delivery";

const STATUS_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "Tous les statuts" },
  { value: "pending", label: "En attente d'affectation" },
  { value: "assigned", label: "Affectées" },
  { value: "picked_up", label: "Colis récupéré" },
  { value: "in_transit", label: "En transit" },
  { value: "out_for_delivery", label: "En livraison" },
  { value: "delivered", label: "Livrées" },
  { value: "delivery_failed", label: "Échecs" },
  { value: "returned", label: "Retournées" },
];

export default function PartnerDeliveriesPage() {
  const { data: deliveries, loading, error, refetch } = useAsync(() => partnerApi.listPartnerDeliveries(), []);
  const [status, setStatus] = useState("all");

  const filtered = deliveries?.filter((d) => status === "all" || d.status === status) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
          <MapPin className="h-6 w-6 text-orange" /> Livraisons de l'entreprise
        </h1>
        <FilterBar
          filters={[{ key: "status", label: "Statut", options: STATUS_FILTER_OPTIONS, value: status }]}
          onChange={(_key, value) => setStatus(value)}
          onReset={() => setStatus("all")}
        />
      </div>

      {loading ? (
        <Spinner label="Chargement des livraisons…" />
      ) : error ? (
        <ErrorState fullPage onRetry={refetch} />
      ) : filtered.length === 0 ? (
        <EmptyState icon={PackageSearch} title="Aucune livraison" description="Les courses confiées à votre entreprise apparaîtront ici." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((delivery) => (
            <Link key={delivery.id} to={`/partner-delivery?delivery=${delivery.id}`}>
              <Card variant="interactive" className="flex h-full flex-col justify-between gap-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-muted-foreground">
                      {delivery.reference || delivery.id.slice(0, 8)}
                    </p>
                    <p className="truncate font-semibold text-ink">Commande n°{delivery.order.slice(0, 8)}</p>
                  </div>
                  <Badge variant={DELIVERY_STATUS_VARIANT[delivery.status]} size="sm">
                    {DELIVERY_STATUS_LABEL[delivery.status]}
                  </Badge>
                </div>
                <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span className="truncate">
                    {delivery.driver_detail?.full_name || "Livreur non affecté"} · {formatDate(delivery.created_at)}
                  </span>
                  <ChevronRight className="h-4 w-4 shrink-0" />
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}