import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, ClipboardList } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import { formatDate, formatPrice } from "@/lib/utils";
import type { Driver } from "@/types";

const DELIVERY_STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  delivered: "success",
  picked_up: "warning",
  assigned: "warning",
  pending: "default",
  cancelled: "danger",
};

const PAGE_SIZE = 20;

const STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  delivered: "success",
  paid: "success",
  processing: "warning",
  shipped: "warning",
  pending: "default",
  cancelled: "danger",
};

export default function AdminOrdersPage() {
  const [page, setPage] = useState(1);
  const { data: result, loading, error, refetch } = useAsync(() => ordersApi.listOrdersPaginated({ page }), [page]);
  const [assigningDeliveryId, setAssigningDeliveryId] = useState<string | null>(null);

  const orders = useMemo(() => result?.results ?? [], [result]);
  const totalPages = result ? Math.max(1, Math.ceil(result.count / PAGE_SIZE)) : 1;

  // Chargement des livreurs par boutique (affectation = proximité de la
  // boutique : on ne propose que les livreurs dans le rayon de la commande).
  const pendingStoreIds = useMemo(
    () => [...new Set(orders.filter((o) => o.delivery?.status === "pending").map((o) => (o as { store: string }).store))],
    [orders],
  );
  const [driversByStore, setDriversByStore] = useState<Record<string, Driver[]>>({});

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const entries: Record<string, Driver[]> = {};
      for (const storeId of pendingStoreIds) {
        try {
          entries[storeId] = await ordersApi.listAvailableDrivers(storeId);
        } catch {
          entries[storeId] = [];
        }
      }
      if (!cancelled) setDriversByStore(entries);
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [pendingStoreIds]);

  async function assign(deliveryId: string, driverId: string) {
    if (!driverId) return;
    setAssigningDeliveryId(deliveryId);
    try {
      await ordersApi.assignDriver(deliveryId, driverId);
      refetch();
    } catch {
      // La règle de proximité est re-vérifiée côté serveur : si le livreur
      // s'est éloigné, l'affectation est refusée, on rafraîchit simplement.
      refetch();
    } finally {
      setAssigningDeliveryId(null);
    }
  }

  return (
    <div>
      <h1 className="mb-6 flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
        <ClipboardList className="h-6 w-6 text-orange" /> Commandes
      </h1>

      {loading ? (
        <Spinner label="Chargement des commandes…" />
      ) : error ? (
        <ErrorState fullPage onRetry={refetch} />
      ) : orders.length === 0 ? (
        <EmptyState icon={ClipboardList} title="Aucune commande pour le moment" />
      ) : (
        <>
          <div className="flex flex-col gap-3">
            {orders.map((order) => (
              <Link key={order.id} to={`/admin-order-detail?order=${order.id}`}>
                <Card variant="interactive" className="flex items-center justify-between">
                  <div>
                    <p className="font-semibold text-ink">{order.store_name}</p>
                    <p className="text-xs text-muted-foreground">
                      {order.customer_name} — {formatDate(order.created_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant={STATUS_VARIANT[order.status] ?? "default"}>{order.status}</Badge>
                    <p className="font-bold text-ink">{formatPrice(order.total_amount)}</p>
                    {order.delivery?.status === "pending" ? (
                      <select
                        disabled={assigningDeliveryId === order.delivery.id}
                        onChange={(e) => order.delivery && assign(order.delivery.id, e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        defaultValue=""
                        className="focus-ring rounded-lg border border-border px-2 py-1.5 text-xs transition-colors hover:border-orange/50"
                      >
                        <option value="" disabled>
                          Affecter un livreur…
                        </option>
                        {(driversByStore[order.store] ?? []).map((driver) => (
                          <option key={driver.id} value={driver.id}>
                            {driver.full_name}
                            {driver.distance_km != null ? ` — ${driver.distance_km.toFixed(1)} km` : ""}
                          </option>
                        ))}
                      </select>
                    ) : (
                      order.delivery && (
                        <Badge variant={DELIVERY_STATUS_VARIANT[order.delivery.status] ?? "default"}>
                          Livraison : {order.delivery.status}
                        </Badge>
                      )
                    )}
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                  </div>
                </Card>
              </Link>
            ))}
          </div>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} className="mt-6" />
        </>
      )}
    </div>
  );
}
