import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, Clock, Package, ShoppingBag, Store as StoreIcon, TriangleAlert, Wallet } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as catalogApi from "@/api/catalog";
import * as ordersApi from "@/api/orders";
import { Card, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { KycStatusCard } from "@/components/kyc/KycStatusCard";
import { formatDate, formatPrice } from "@/lib/utils";
import type { Driver } from "@/types";

const STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  delivered: "success",
  paid: "success",
  processing: "warning",
  shipped: "warning",
  pending: "default",
  cancelled: "danger",
};

export default function MerchantDashboardPage() {
  const { data: own, loading: loadingStores } = useAsync(() => catalogApi.listMyStores(), []);
  const { data: orders, loading: loadingOrders, refetch: refetchOrders } = useAsync(() => ordersApi.listOrders(), []);
  const [assigningDeliveryId, setAssigningDeliveryId] = useState<string | null>(null);

  // Livreurs proposés par boutique (affectation = proximité de la boutique).
  const orderList = useMemo(() => orders ?? [], [orders]);
  const pendingStoreIds = useMemo(
    () => [...new Set(orderList.filter((o) => o.delivery?.status === "pending").map((o) => o.store))],
    [orderList],
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

  if (loadingStores || loadingOrders) return <Spinner label="Chargement du tableau de bord…" />;
  if (!own) return null;
  const revenue = orders?.reduce((sum, o) => sum + parseFloat(o.total_amount), 0) ?? 0;

  async function assign(deliveryId: string, driverId: string) {
    if (!driverId) return;
    setAssigningDeliveryId(deliveryId);
    try {
      await ordersApi.assignDriver(deliveryId, driverId);
      refetchOrders();
    } finally {
      setAssigningDeliveryId(null);
    }
  }

  if (own.length === 0) {
    return (
      <div className="flex flex-col gap-6">
        <KycStatusCard kind="seller" />
        <EmptyState
          icon={StoreIcon}
          title="Vous n'avez pas encore de boutique"
          description="Créez votre boutique pour commencer à publier des produits."
          action={
            <Link to="/create-shop">
              <Button>Créer ma boutique</Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl text-ink">Tableau de bord</h1>

      <KycStatusCard kind="seller" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent text-orange">
            <Wallet className="h-5 w-5" />
          </span>
          <div>
            <p className="text-xs text-muted-foreground">Chiffre d'affaires</p>
            <p className="text-lg font-semibold text-ink">{formatPrice(revenue)}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent text-orange">
            <ShoppingBag className="h-5 w-5" />
          </span>
          <div>
            <p className="text-xs text-muted-foreground">Commandes</p>
            <p className="text-lg font-semibold text-ink">{orders?.length ?? 0}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent text-orange">
            <Package className="h-5 w-5" />
          </span>
          <div>
            <p className="text-xs text-muted-foreground">Boutiques</p>
            <p className="text-lg font-semibold text-ink">{own.length}</p>
          </div>
        </Card>
      </div>

      {own.map((store) => (
        <Card key={store.id} className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <p className="font-semibold text-ink">{store.name}</p>
            <Badge variant={store.status === "active" ? "success" : store.status === "suspended" ? "danger" : "warning"}>
              {store.status === "active" ? "Approuvée" : store.status === "suspended" ? "Rejetée" : "En attente de validation"}
            </Badge>
          </div>
          {store.status === "inactive" && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="h-3.5 w-3.5 shrink-0" />
              Votre boutique est en cours de vérification par notre équipe.
            </p>
          )}
          {store.status === "suspended" && store.rejection_reason && (
            <p className="flex items-center gap-1.5 text-xs text-danger">
              <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
              Raison : {store.rejection_reason}
            </p>
          )}
        </Card>
      ))}

      <Card>
        <CardTitle>Dernières commandes</CardTitle>
        {orders?.length === 0 ? (
          <div className="mt-3">
            <EmptyState icon={ShoppingBag} title="Aucune commande reçue" />
          </div>
        ) : (
          <div className="mt-3 flex flex-col gap-3">
            {orders?.slice(0, 5).map((order) => (
              <div key={order.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 text-sm">
                <span className="text-muted-foreground">{formatDate(order.created_at)}</span>
                <Badge variant={STATUS_VARIANT[order.status] ?? "default"}>{order.status}</Badge>
                <span className="font-bold text-ink">{formatPrice(order.total_amount)}</span>
                {order.delivery?.status === "pending" ? (
                  <select
                    disabled={assigningDeliveryId === order.delivery.id}
                    onChange={(e) => order.delivery && assign(order.delivery.id, e.target.value)}
                    defaultValue=""
                    className="focus-ring rounded-lg border border-border px-2 py-1.5 text-xs transition-colors hover:border-orange/50"
                  >
                    <option value="" disabled>
                      Affecter un livreur…
                    </option>
                    {driversByStore[order.store]?.map((driver) => (
                      <option key={driver.id} value={driver.id}>
                        {driver.full_name}
                        {driver.distance_km != null ? ` — ${driver.distance_km.toFixed(1)} km` : ""}
                      </option>
                    ))}
                  </select>
                ) : (
                  order.delivery && <Badge variant="default">Livraison : {order.delivery.status}</Badge>
                )}
                <Link
                  to={`/order-detail?order=${order.id}`}
                  aria-label="Voir le détail de la commande"
                  className="focus-ring rounded-full p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-orange"
                >
                  <ChevronRight className="h-4 w-4" />
                </Link>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
