import { Link } from "react-router-dom";
import { Building2, ChevronRight, PackageSearch } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { formatDate, formatPrice } from "@/lib/utils";
import type { GlobalOrder } from "@/types";

const STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  delivered: "success",
  paid: "success",
  processing: "warning",
  shipped: "warning",
  pending: "default",
  cancelled: "danger",
};

export default function OrdersPage() {
  const { data, loading, error, refetch } = useAsync(async () => {
    const [globals, orders] = await Promise.all([
      ordersApi.listGlobalOrders(),
      ordersApi.listOrders(),
    ]);
    // Les commandes simples qui ne sont PAS des sous-commandes d'une commande
    // globale (commande une boutique historique) s'affichent également.
    const standalone = orders.filter((o) => !o.global_order);
    return { globals, standalone };
  }, []);

  if (loading) return <Spinner label="Chargement de vos commandes…" />;

  const globals = data?.globals ?? [];
  const standalone = data?.standalone ?? [];
  const isEmpty = globals.length === 0 && standalone.length === 0;

  return (
    <div>
      <h1 className="mb-6 font-display text-2xl font-bold text-gray-900">Mes commandes</h1>
      {error ? (
        <ErrorState fullPage onRetry={refetch} />
      ) : isEmpty ? (
        <EmptyState
          icon={PackageSearch}
          title="Vous n'avez pas encore passé de commande"
          description="Vos commandes apparaîtront ici une fois validées."
          action={
            <Link to="/search">
              <Button>Découvrir des produits</Button>
            </Link>
          }
        />
      ) : (
        <div className="flex flex-col gap-3">
          {globals.map((order) => (
            <GlobalOrderCard key={order.id} order={order} />
          ))}
          {standalone.map((order) => (
            <Link key={order.id} to={`/tracking?order=${order.id}`}>
              <Card variant="interactive" className="flex items-center justify-between">
                <div>
                  <p className="font-semibold text-ink">{order.store_name}</p>
                  <p className="text-xs text-muted-foreground">{formatDate(order.created_at)}</p>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant={STATUS_VARIANT[order.status] ?? "default"}>{order.status}</Badge>
                  <p className="font-bold text-ink">{formatPrice(order.total_amount)}</p>
                  <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" />
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function GlobalOrderCard({ order }: { order: GlobalOrder }) {
  const singleStoreName =
    order.number_of_stores === 1 ? (order.orders[0]?.store_name ?? null) : null;
  return (
    <Link to={`/tracking?gorder=${order.id}`}>
      <Card variant="interactive" className="flex items-center justify-between">
        <div className="min-w-0">
          <p className="inline-flex items-center gap-2 font-semibold text-ink">
            <Building2 className="h-4 w-4 shrink-0 text-orange" />
            {singleStoreName ?? `${order.number_of_stores} boutiques`}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono">{order.reference}</code>
            <span>{formatDate(order.created_at)}</span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <Badge variant={STATUS_VARIANT[order.status] ?? "default"}>{order.status}</Badge>
          <p className="font-bold text-ink">{formatPrice(order.total_amount)}</p>
          <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" />
        </div>
      </Card>
    </Link>
  );
}