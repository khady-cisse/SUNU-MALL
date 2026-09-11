import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Clock, MapPin, PackageCheck, PackageSearch, RefreshCw, Search, Truck, XCircle } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import * as paymentsApi from "@/api/payments";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { apiErrorMessage } from "@/lib/api";
import { formatDate, formatEta, formatPrice } from "@/lib/utils";
import type { Address, DeliveryEvent, DeliveryStatus, GlobalOrder, Order } from "@/types";

const PAYMENT_STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  success: "success",
  pending: "warning",
  failed: "danger",
  refunded: "default",
};

const DeliveryMap = lazy(() => import("@/components/marketplace/DeliveryMap").then((m) => ({ default: m.DeliveryMap })));

const STEPS: { key: DeliveryStatus; label: string; icon: typeof Clock }[] = [
  { key: "pending", label: "En attente", icon: Clock },
  { key: "assigned", label: "Livreur affecté", icon: PackageCheck },
  { key: "picked_up", label: "En cours de livraison", icon: Truck },
  { key: "delivered", label: "Livrée", icon: CheckCircle2 },
];

/**
 * Suivi d'une commande — un seul suivi par commande, même multi-boutiques :
 * tous les produits arrivent ensemble dans la même livraison. Mode connecté
 * (`?order=` ou `?gorder=`, flux SSE + resynchronisation) ou invité
 * (`POST /orders/track/` avec référence + email, spec §16 achat sans compte).
 */
export default function TrackingPage() {
  const [searchParams] = useSearchParams();
  const orderId = searchParams.get("order");
  const gorderId = searchParams.get("gorder");
  const isAuthMode = Boolean(orderId || gorderId);

  const { data: authData, refetch } = useAsync(
    () =>
      orderId
        ? (ordersApi.getOrder(orderId) as Promise<Order | GlobalOrder | null>)
        : gorderId
          ? (ordersApi.getGlobalOrder(gorderId) as Promise<Order | GlobalOrder | null>)
          : Promise.resolve(null),
    [orderId, gorderId],
  );

  // Suivi invité : référence + email, sans JWT.
  const [reference, setReference] = useState("");
  const [email, setEmail] = useState("");
  const [guestResult, setGuestResult] = useState<Order | GlobalOrder | null>(null);
  const [tracking, setTracking] = useState(false);
  const [trackError, setTrackError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // État "live" porté par le flux SSE ; tant qu'il est null, on affiche les
  // données REST. Chaque événement transporte l'état complet de la livraison.
  const [live, setLive] = useState<DeliveryEvent | null>(null);
  const [sseConnected, setSseConnected] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);

  // La commande suivie : commande simple OU commande globale multi-boutiques
  // (une seule livraison pour tous les produits, quelque soit le mode).
  const authGlobal: GlobalOrder | null =
    isAuthMode && !!authData && "number_of_stores" in authData ? (authData as GlobalOrder) : null;
  const order: Order | null = isAuthMode ? (authGlobal ? null : (authData as Order | null)) : null;
  const global: GlobalOrder | null = authGlobal ?? (
    guestResult && "number_of_stores" in guestResult ? (guestResult as GlobalOrder) : null
  );
  const guestOrder: Order | null =
    !isAuthMode && guestResult && !("number_of_stores" in guestResult) ? (guestResult as Order) : null;
  const tracked: Order | GlobalOrder | null = order ?? global ?? guestOrder;

  const delivery = (order?.delivery ?? global?.delivery) || null;
  const deliveryId = delivery?.id ?? null;

  // Temps réel et polling de secours : uniquement en mode connecté — le flux
  // SSE et la resynchronisation REST exigent un JWT.
  useEffect(() => {
    if (!isAuthMode || !deliveryId) return;
    const source = ordersApi.subscribeDeliveryEvents(deliveryId, (event) => {
      setSseConnected(true);
      setLive(event);
      if (event.event === "status" || event.event === "assigned") refetch();
    });
    source.onopen = () => setSseConnected(true);
    source.onerror = () => setSseConnected(false);
    return () => source.close();
  }, [isAuthMode, deliveryId, refetch]);

  useEffect(() => {
    if (!isAuthMode || (!orderId && !gorderId) || sseConnected) return;
    const interval = setInterval(refetch, 10000);
    return () => clearInterval(interval);
  }, [isAuthMode, orderId, gorderId, refetch, sseConnected]);

  async function handleTrack(e: React.FormEvent) {
    e.preventDefault();
    setTrackError(null);
    setGuestResult(null);
    setLive(null);
    if (!reference.trim() || !email.trim()) {
      setTrackError("Renseignez la référence de la commande et l'adresse email utilisée pour commander.");
      return;
    }
    setTracking(true);
    try {
      setGuestResult(await ordersApi.trackOrder(reference.trim(), email.trim()));
    } catch (err) {
      setTrackError(apiErrorMessage(err, "Aucune commande ne correspond à cette référence et à cet email."));
    } finally {
      setTracking(false);
    }
  }

  async function handleCancel() {
    if (!tracked) return;
    const label = global ? global.reference : `n°${order!.id.slice(0, 8)}`;
    if (!confirm(`Annuler la commande ${global ? label : label} ?`)) return;
    setCancelling(true);
    try {
      if (global) await ordersApi.cancelGlobalOrder(global.id);
      else if (order) await ordersApi.cancelOrder(order.id);
      refetch();
    } finally {
      setCancelling(false);
    }
  }

  async function handleRetryPayment() {
    if (!tracked?.payment) return;
    setRetrying(true);
    try {
      const result = await paymentsApi.initiatePayment(tracked.payment.id);
      if (result.sandbox) {
        await paymentsApi.sandboxConfirmPayment(tracked.payment.id, "success");
      }
      refetch();
    } finally {
      setRetrying(false);
    }
  }

  // Mode invité, avant recherche — formulaire référence + email.
  if (!isAuthMode && !guestResult) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="font-display text-2xl font-bold text-gray-900">Suivre ma commande</h1>
        <Card className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            Vous avez commandé sans compte ? Renseignez la référence indiquée dans votre email de confirmation
            et l'adresse utilisée pour commander. Le suivi fonctionne depuis n'importe quel appareil, sans connexion.
          </p>
          <form onSubmit={handleTrack} className="flex flex-col gap-3 sm:flex-row sm:items-start">
            <div className="flex-1">
              <Input
                label="Référence de la commande"
                placeholder="SM-20250101-000001"
                autoCapitalize="characters"
                value={reference}
                onChange={(e) => setReference(e.target.value)}
              />
            </div>
            <div className="flex-1">
              <Input
                label="Email utilisé"
                type="email"
                placeholder="jean@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <Button type="submit" loading={tracking} className="shrink-0">
              <Search className="h-4 w-4" />
              Suivre
            </Button>
          </form>
          {trackError && (
            <p className="rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">{trackError}</p>
          )}
        </Card>
        <Link to="/orders" className="text-sm font-medium text-navy underline">
          Se connecter pour retrouver mes commandes
        </Link>
      </div>
    );
  }

  // Aucun résultat : chargement (mode connecté) ou introuvable.
  if (!tracked && !guestOrder && !guestResult) {
    return isAuthMode ? (
      <Spinner label="Chargement du suivi…" />
    ) : (
      <EmptyState icon={PackageSearch} title="Aucune commande trouvée" />
    );
  }
  if (!tracked) {
    return <Spinner label="Chargement du suivi…" />;
  }

  const isGlobal = !!global;
  const title = isGlobal
    ? `Commande ${(tracked as GlobalOrder).reference}`
    : `Commande n°${(tracked as Order).id.slice(0, 8)}`;
  const storeLine = isGlobal
    ? `${(tracked as GlobalOrder).number_of_stores} boutique(s) — les produits arrivent ensemble`
    : (tracked as Order).store_name;
  const canCancel = isGlobal
    ? (tracked as GlobalOrder).status !== "cancelled"
    : (tracked as Order).can_be_cancelled;
  const addressDetail: Address | null =
    isGlobal
      ? ((tracked as GlobalOrder).address_detail ?? null)
      : ((tracked as Order).address_detail ?? null);

  const deliveryStatus = live?.status ?? delivery?.status;
  const lastPosition = live?.last_position ?? delivery?.last_position ?? null;
  const deliveryEta = live?.eta_seconds ?? delivery?.eta_seconds ?? null;
  const liveMessage = live?.message ?? "";

  const currentIndex = Math.max(0, STEPS.findIndex((s) => s.key === deliveryStatus));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold text-gray-900">Suivi de livraison</h1>
      <Card className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-ink">{title}</p>
            <p className="text-sm text-muted-foreground">{storeLine}</p>
          </div>
          <div className="flex items-center gap-2">
            {isAuthMode && !sseConnected && (
              <Badge variant="warning">Mode secours (actualisation 10 s)</Badge>
            )}
            {isAuthMode && canCancel && (
              <Button variant="danger" size="sm" onClick={handleCancel} loading={cancelling}>
                <XCircle className="h-4 w-4" />
                Annuler la commande
              </Button>
            )}
            {!isAuthMode && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setGuestResult(null);
                  setTrackError(null);
                  setLive(null);
                }}
              >
                Suivre une autre commande
              </Button>
            )}
          </div>
        </div>

        {liveMessage && (
          <div className="rounded-lg border border-orange/30 bg-orange-50 p-3 text-xs font-medium text-orange-800">
            {liveMessage}
          </div>
        )}

        {isAuthMode && tracked.payment?.status === "failed" && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-danger/30 bg-red-50 p-3">
            <Badge variant={PAYMENT_STATUS_VARIANT[tracked.payment.status]}>Paiement échoué</Badge>
            <p className="flex-1 text-xs text-danger">Le paiement n'a pas abouti.</p>
            <Button size="sm" onClick={handleRetryPayment} loading={retrying}>
              Réessayer le paiement
            </Button>
          </div>
        )}

        {tracked.payment?.refund && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
            <Badge variant={tracked.payment.refund.status === "completed" ? "success" : "warning"}>
              {tracked.payment.refund.status === "completed" ? "Remboursé" : "Remboursement en attente"}
            </Badge>
            <p className="flex-1 text-xs text-amber-800">
              {tracked.payment.refund.status === "completed"
                ? `Remboursé le ${tracked.payment.refund.refunded_at ? formatDate(tracked.payment.refund.refunded_at) : ""}.`
                : "Votre remboursement est en cours de traitement."}
            </p>
          </div>
        )}

        <div className="flex items-start">
          {STEPS.map((step, i) => (
            <div key={step.key} className="flex flex-1 items-center last:flex-none">
              <div className="flex flex-col items-center gap-2 text-center">
                <span
                  className={`grid h-10 w-10 shrink-0 place-items-center rounded-full transition-colors ${
                    i <= currentIndex ? "bg-gradient-orange text-white shadow-orange" : "bg-muted text-muted-foreground"
                  }`}
                >
                  <step.icon className="h-5 w-5" />
                </span>
                <p className={`text-xs font-medium ${i <= currentIndex ? "text-gray-700" : "text-muted-foreground"}`}>{step.label}</p>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`mb-6 h-0.5 flex-1 rounded-full transition-colors ${i < currentIndex ? "bg-orange" : "bg-border"}`} />
              )}
            </div>
          ))}
        </div>
        {delivery?.driver_detail && (
          <div className="flex items-center gap-3 border-t border-border pt-4">
            <Truck className="h-5 w-5 text-orange" />
            <div>
              <p className="text-sm font-medium text-ink">{delivery.driver_detail.full_name}</p>
              <p className="text-xs text-muted-foreground">{delivery.driver_detail.phone}</p>
            </div>
          </div>
        )}
        {deliveryStatus === "picked_up" && !isGlobal && isAuthMode && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-accent bg-muted/40 p-3">
            <p className="text-sm text-ink">
              <strong>Votre colis est arrivé.</strong> Le livreur vous remet un code de confirmation : validez la réception pour
              finaliser votre commande.
            </p>
            <Link
              to={`/delivery-confirm?order=${(tracked as Order).id}`}
              className="btn-orange focus-ring inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold"
            >
              <PackageCheck className="h-4 w-4" />
              Confirmer la réception
            </Link>
          </div>
        )}
        {(lastPosition || (addressDetail?.latitude != null && addressDetail?.longitude != null)) && (
          <div className="border-t border-border pt-4">
            <Suspense fallback={<div className="h-56 w-full animate-pulse rounded-2xl bg-muted" />}>
              <DeliveryMap
                driverPosition={
                  lastPosition
                    ? {
                        lat: parseFloat(lastPosition.latitude),
                        lng: parseFloat(lastPosition.longitude),
                        label: "Position du livreur",
                      }
                    : null
                }
                destination={
                  addressDetail?.latitude != null && addressDetail?.longitude != null
                    ? {
                        lat: parseFloat(addressDetail.latitude),
                        lng: parseFloat(addressDetail.longitude),
                        label: "Votre adresse",
                      }
                    : null
                }
                className="h-56 w-full"
              />
            </Suspense>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              {lastPosition && (
                <p className="flex items-center gap-1.5">
                  <MapPin className="h-3.5 w-3.5 text-orange" />
                  Position mise à jour {formatDate(lastPosition.recorded_at)}
                </p>
              )}
              {deliveryEta != null && deliveryStatus !== "delivered" && (
                <p className="flex items-center gap-1.5">
                  <Clock className="h-3.5 w-3.5 text-orange" />
                  Arrivée estimée : {formatEta(deliveryEta)}
                </p>
              )}
            </div>
          </div>
        )}
        {trackError && (
          <p className="rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">{trackError}</p>
        )}
        {!isAuthMode && (
          <div className="flex items-center gap-2 border-t border-border pt-4">
            <Button variant="ghost" size="sm" onClick={async () => {
              if (!reference.trim() || !email.trim()) return;
              setRefreshing(true);
              setTrackError(null);
              try {
                setGuestResult(await ordersApi.trackOrder(reference.trim(), email.trim()));
              } catch (err) {
                setTrackError(apiErrorMessage(err, "Aucune commande ne correspond à cette référence et à cet email."));
              } finally {
                setRefreshing(false);
              }
            }} loading={refreshing}>
              <RefreshCw className="h-4 w-4" />
              Actualiser
            </Button>
            {guestOrder && (
              <p className="text-xs text-muted-foreground">
                Total : <strong className="text-orange">{formatPrice(guestOrder.total_amount)}</strong>
              </p>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}