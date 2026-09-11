import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, PackageX } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatPrice } from "@/lib/utils";
import type { GlobalOrder, Order } from "@/types";

export default function OrderConfirmedPage() {
  const [searchParams] = useSearchParams();
  const orderId = searchParams.get("order");
  const globalOrderId = searchParams.get("gorder");
  const { data: order, loading } = useAsync(
    () => {
      if (orderId) return ordersApi.getOrder(orderId) as Promise<Order | GlobalOrder | null>;
      if (globalOrderId) return ordersApi.getGlobalOrder(globalOrderId) as Promise<Order | GlobalOrder | null>;
      return Promise.resolve(null) as Promise<Order | GlobalOrder | null>;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [orderId, globalOrderId],
  );

  if (!orderId && !globalOrderId) return <EmptyState icon={PackageX} title="Aucune commande à afficher" />;
  if (loading) return <Spinner label="Chargement de votre commande…" />;
  if (!order) return <EmptyState icon={PackageX} title="Commande introuvable" />;

  const isGlobal = "number_of_stores" in order;

  const summary = isGlobal
    ? (() => {
        const g = order as GlobalOrder;
        return {
          id: order.id,
          storeName:
            g.number_of_stores > 1 ? `${g.number_of_stores} boutiques` : (g.orders[0]?.store_name ?? "boutique"),
          total: order.total_amount,
        };
      })()
    : {
        id: order.id,
        storeName: (order as Order).store_name,
        total: order.total_amount,
      };

  return (
    <div className="flex flex-col items-center gap-4 py-10 text-center">
      <div className="relative">
        <img
          src="/order-handoff.jpg"
          alt="Remise de commande Sunu Mall"
          className="h-40 w-40 rounded-full border-4 border-white object-cover shadow-xl sm:h-48 sm:w-48"
        />
        <span className="absolute -bottom-2 -right-2 grid h-14 w-14 place-items-center rounded-full border-4 border-white bg-green-100 shadow-md">
          <CheckCircle2 className="h-7 w-7 text-success" />
        </span>
      </div>
      <h1 className="font-display text-2xl font-extrabold text-gray-900">Commande confirmée !</h1>
      <p className="text-sm text-muted-foreground">
        {isGlobal ? summary.storeName : `Commande n°${summary.id.slice(0, 8)}`} — <strong className="text-ink">{summary.storeName}</strong> -{" "}
        <strong className="text-orange">{formatPrice(summary.total)}</strong>
      </p>
      <p className="text-sm text-muted-foreground">
        Vos produits sont regroupés en une seule livraison : le suivi se fait sur l'ensemble de la commande.
      </p>
      <div className="flex gap-3">
        <Link to={isGlobal ? `/tracking?gorder=${summary.id}` : `/tracking?order=${summary.id}`}>
          <Button>Suivre ma livraison</Button>
        </Link>
        <Link to="/orders">
          <Button variant="secondary">Voir mes commandes</Button>
        </Link>
      </div>
    </div>
  );
}