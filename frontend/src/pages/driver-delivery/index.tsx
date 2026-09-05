import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, MapPin, Navigation, PackageSearch, Satellite, Truck } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatDate, formatPrice } from "@/lib/utils";
import type { DeliveryStatus } from "@/types";

const DeliveryMap = lazy(() => import("@/components/marketplace/DeliveryMap").then((m) => ({ default: m.DeliveryMap })));

const NEXT_STATUS: Partial<Record<DeliveryStatus, DeliveryStatus>> = {
  assigned: "picked_up",
  picked_up: "delivered",
};

const NEXT_LABEL: Partial<Record<DeliveryStatus, string>> = {
  assigned: "Marquer « colis récupéré »",
  picked_up: "Marquer « livré »",
};

export default function DriverDeliveryPage() {
  const [searchParams] = useSearchParams();
  const deliveryId = searchParams.get("delivery");
  const [updating, setUpdating] = useState(false);
  const [sharingPosition, setSharingPosition] = useState(false);
  const [autoTracking, setAutoTracking] = useState(false);
  const [positionMessage, setPositionMessage] = useState<string | null>(null);
  const lastSentAt = useRef(0);

  const { data: delivery, loading: loadingDelivery, refetch } = useAsync(
    () => (deliveryId ? ordersApi.getDelivery(deliveryId) : Promise.resolve(null)),
    [deliveryId],
  );
  const { data: order, loading: loadingOrder } = useAsync(
    () => (delivery ? ordersApi.getOrder(delivery.order) : Promise.resolve(null)),
    [delivery?.order],
  );

  // Suivi automatique : watchPosition envoie la position au serveur au fil de
  // l'eau (~1 requête / 4 s), diffusée ensuite en temps réel au client (SSE).
  useEffect(() => {
    if (!autoTracking || !deliveryId) return;
    if (!("geolocation" in navigator)) {
      setPositionMessage("Localisation non prise en charge par ce navigateur.");
      setAutoTracking(false);
      return;
    }
    let cancelled = false;
    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        const now = Date.now();
        if (cancelled || now - lastSentAt.current < 4000) return;
        lastSentAt.current = now;
        ordersApi
          .shareDeliveryPosition(deliveryId, pos.coords.latitude, pos.coords.longitude)
          .then(() => setPositionMessage("Position transmise en continu au client."))
          .catch(() => setPositionMessage("Échec d'envoi de la position (nouvel essai…)."));
      },
      () => {
        if (!cancelled) {
          setPositionMessage("Localisation refusée ou indisponible — suivi automatique arrêté.");
          setAutoTracking(false);
        }
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 },
    );
    return () => {
      cancelled = true;
      navigator.geolocation.clearWatch(watchId);
    };
  }, [autoTracking, deliveryId]);

  if (!deliveryId) return <EmptyState icon={PackageSearch} title="Sélectionnez une course" description="Choisissez une course depuis « Mes courses »." />;
  if (loadingDelivery || (delivery && loadingOrder)) return <Spinner label="Chargement de la course…" />;
  if (!delivery) return <EmptyState icon={PackageSearch} title="Course introuvable" />;

  const next = NEXT_STATUS[delivery.status];

  async function advanceStatus() {
    if (!next || !deliveryId) return;
    setUpdating(true);
    try {
      await ordersApi.updateDeliveryStatus(deliveryId, next);
      refetch();
    } finally {
      setUpdating(false);
    }
  }

  function sharePosition() {
    if (!deliveryId || !navigator.geolocation) return;
    setSharingPosition(true);
    setPositionMessage(null);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          await ordersApi.shareDeliveryPosition(deliveryId, pos.coords.latitude, pos.coords.longitude);
          setPositionMessage("Position partagée avec le client.");
          refetch();
        } catch {
          setPositionMessage("Impossible d'envoyer la position.");
        } finally {
          setSharingPosition(false);
        }
      },
      () => {
        setPositionMessage("Localisation refusée ou indisponible.");
        setSharingPosition(false);
      },
    );
  }

  const driverPosition = delivery.last_position
    ? {
        lat: parseFloat(delivery.last_position.latitude),
        lng: parseFloat(delivery.last_position.longitude),
        label: "Votre position",
      }
    : null;
  const destination =
    order?.address_detail?.latitude != null && order?.address_detail?.longitude != null
      ? {
          lat: parseFloat(order.address_detail.latitude),
          lng: parseFloat(order.address_detail.longitude),
          label: "Adresse de livraison",
        }
      : null;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
        <Truck className="h-6 w-6 text-orange" /> Détail de la course
      </h1>
      <Card className="flex flex-col gap-3">
        {order && (
          <>
            <p className="font-semibold text-ink">{order.store_name}</p>
            <p className="text-sm text-muted-foreground">{formatDate(order.created_at)}</p>
            <div className="flex items-center gap-2 text-sm text-ink">
              <MapPin className="h-4 w-4 shrink-0 text-orange" />
              {order.address_detail?.street}, {order.address_detail?.city}
            </div>
            <p className="text-sm font-bold text-orange">{formatPrice(order.total_amount)}</p>
          </>
        )}

        {driverPosition || destination ? (
          <Suspense fallback={<div className="h-56 w-full animate-pulse rounded-2xl bg-muted" />}>
            <DeliveryMap driverPosition={driverPosition} destination={destination} className="h-56 w-full" />
          </Suspense>
        ) : (
          <div className="rounded-lg border border-dashed border-border bg-muted/40 px-3 py-4 text-center text-xs text-muted-foreground">
            Aucune position à afficher pour l'instant. Partagez votre position pour l'afficher sur la carte.
          </div>
        )}

        <p className="border-t border-border pt-3 text-sm">
          Statut actuel : <strong className="text-ink">{delivery.status}</strong>
        </p>

        {next ? (
          <Button onClick={advanceStatus} loading={updating}>
            {NEXT_LABEL[delivery.status]}
          </Button>
        ) : (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            {delivery.status === "delivered" && <CheckCircle2 className="h-4 w-4 text-success" />}
            {delivery.status === "delivered" ? "Livraison terminée." : "En attente d'affectation par le commerçant."}
          </p>
        )}

        {(delivery.status === "assigned" || delivery.status === "picked_up") && (
          <>
            <Button variant="secondary" onClick={sharePosition} loading={sharingPosition}>
              <Navigation className="h-4 w-4" />
              Partager ma position
            </Button>
            <Button variant="secondary" onClick={() => setAutoTracking((active) => !active)} className={autoTracking ? "ring-2 ring-orange" : ""}>
              <Satellite className="h-4 w-4" />
              {autoTracking ? "Arrêter le suivi automatique" : "Suivi automatique"}
            </Button>
          </>
        )}
        {autoTracking && (
          <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-xs text-success">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
            </span>
            Suivi GPS actif — le client voit votre position en temps réel.
          </div>
        )}
        {positionMessage && (
          <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
            {positionMessage}
          </div>
        )}
      </Card>
    </div>
  );
}
