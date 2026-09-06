import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CreditCard, MapPin, PackageX, Truck, User, XCircle } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import * as paymentsApi from "@/api/payments";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatDate, formatPrice } from "@/lib/utils";

const ORDER_STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  delivered: "success",
  paid: "success",
  processing: "warning",
  shipped: "warning",
  pending: "default",
  cancelled: "danger",
};

const DELIVERY_STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  delivered: "success",
  picked_up: "warning",
  assigned: "warning",
  pending: "default",
  cancelled: "danger",
};

const PAYMENT_STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  success: "success",
  pending: "warning",
  failed: "danger",
  refunded: "default",
};

export default function OrderDetailPage() {
  const [searchParams] = useSearchParams();
  const orderId = searchParams.get("order");
  const { data: order, loading, refetch } = useAsync(
    () => (orderId ? ordersApi.getOrder(orderId) : Promise.resolve(null)),
    [orderId],
  );
  const { data: drivers } = useAsync(
    () => (order?.store ? ordersApi.listAvailableDrivers(order.store) : Promise.resolve([])),
    [order?.store],
  );
  const [assigning, setAssigning] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);

  if (!orderId) return <EmptyState icon={PackageX} title="Aucune commande sélectionnée" />;
  if (loading) return <Spinner label="Chargement de la commande…" />;
  if (!order) return <EmptyState icon={PackageX} title="Commande introuvable" />;

  async function assign(driverId: string) {
    if (!driverId || !order?.delivery) return;
    setAssigning(true);
    try {
      await ordersApi.assignDriver(order.delivery.id, driverId);
      refetch();
    } finally {
      setAssigning(false);
    }
  }

  async function handleCancel() {
    if (!order || !confirm("Annuler cette commande ?")) return;
    setCancelling(true);
    try {
      await ordersApi.cancelOrder(order.id);
      refetch();
    } finally {
      setCancelling(false);
    }
  }

  async function handleRetryPayment() {
    if (!order?.payment) return;
    setRetrying(true);
    try {
      await paymentsApi.sandboxConfirmPayment(order.payment.id, "success");
      refetch();
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex flex-wrap items-center gap-2 font-display text-2xl font-bold text-gray-900">
          Commande n°{order.id.slice(0, 8)}
          <Badge variant={ORDER_STATUS_VARIANT[order.status] ?? "default"}>{order.status}</Badge>
        </h1>
        {order.can_be_cancelled && (
          <Button variant="danger" size="sm" onClick={handleCancel} loading={cancelling}>
            <XCircle className="h-4 w-4" />
            Annuler la commande
          </Button>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="flex flex-col gap-3">
          <h2 className="flex items-center gap-2 font-semibold text-ink">
            <User className="h-4 w-4 text-orange" /> Client
          </h2>
          <div>
            <p className="text-sm font-medium text-ink">{order.customer_name}</p>
            <p className="text-sm text-muted-foreground">{order.customer_email}</p>
          </div>
          <div className="flex items-start gap-1.5 border-t border-border pt-3 text-sm text-ink">
            <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-orange" />
            <span>
              {order.address_detail?.street}, {order.address_detail?.city}, {order.address_detail?.country}
            </span>
          </div>
        </Card>

        <Card className="flex flex-col gap-3">
          <h2 className="flex items-center gap-2 font-semibold text-ink">
            <CreditCard className="h-4 w-4 text-orange" /> Paiement
          </h2>
          {order.payment ? (
            <>
              <div className="flex items-center justify-between">
                <p className="text-sm text-ink">
                  Méthode : <strong className="font-semibold">{order.payment.method}</strong>
                </p>
                <Badge variant={PAYMENT_STATUS_VARIANT[order.payment.status] ?? "default"}>{order.payment.status}</Badge>
              </div>
              {order.payment.status === "failed" && (
                <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 p-3">
                  <p className="flex-1 text-xs text-danger">Le paiement a échoué. Le client peut réessayer.</p>
                  <Button size="sm" onClick={handleRetryPayment} loading={retrying}>
                    Simuler succès
                  </Button>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Aucun paiement associé.</p>
          )}
          <p className="border-t border-border pt-3 text-xs text-muted-foreground">Commandée le {formatDate(order.created_at)}</p>
        </Card>
      </div>

      <Card>
        <h2 className="mb-4 font-semibold text-ink">Articles</h2>
        <div className="flex flex-col gap-2">
          {order.items.map((item) => (
            <div key={item.id} className="flex items-center justify-between border-t border-border pt-2 text-sm first:border-t-0 first:pt-0">
              <span className="text-ink">
                {item.product_name} <span className="text-muted-foreground">× {item.quantity}</span>
              </span>
              <span className="font-semibold text-ink">{formatPrice(parseFloat(item.unit_price) * item.quantity)}</span>
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between border-t border-border pt-3 text-sm">
          <span className="text-muted-foreground">Livraison</span>
          <span className="text-ink">{formatPrice(order.delivery_fee)}</span>
        </div>
        <div className="mt-1 flex items-center justify-between text-sm font-bold text-ink">
          <span>Total</span>
          <span className="text-orange">{formatPrice(order.total_amount)}</span>
        </div>
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="flex items-center gap-2 font-semibold text-ink">
          <Truck className="h-4 w-4 text-orange" /> Livraison
        </h2>
        {order.delivery ? (
          <>
            <div className="flex items-center gap-2">
              <Badge variant={DELIVERY_STATUS_VARIANT[order.delivery.status] ?? "default"}>{order.delivery.status}</Badge>
            </div>
            {order.delivery.driver_detail ? (
              <p className="text-sm text-ink">
                Livreur : <strong className="font-semibold">{order.delivery.driver_detail.full_name}</strong>{" "}
                <span className="text-muted-foreground">{order.delivery.driver_detail.phone}</span>
              </p>
            ) : order.delivery.status === "pending" ? (
              <select
                disabled={assigning}
                onChange={(e) => assign(e.target.value)}
                defaultValue=""
                className="focus-ring w-fit rounded-lg border border-border px-2.5 py-1.5 text-sm transition-colors hover:border-orange/50"
              >
                <option value="" disabled>
                  Affecter un livreur…
                </option>
                {drivers?.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.full_name}
                    {d.distance_km != null ? ` — ${d.distance_km.toFixed(1)} km` : ""}
                  </option>
                ))}
              </select>
            ) : (
              <p className="text-sm text-muted-foreground">Aucun livreur affecté pour l'instant.</p>
            )}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Pas de livraison associée.</p>
        )}
      </Card>
    </div>
  );
}
