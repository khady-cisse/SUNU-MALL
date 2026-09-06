import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, Copy, KeyRound, MapPin, Navigation, PackageSearch, RotateCcw, Satellite, Truck } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import { ApiError } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatDate, formatPrice } from "@/lib/utils";
import type { DeliveryStatus } from "@/types";

const DeliveryMap = lazy(() => import("@/components/marketplace/DeliveryMap").then((m) => ({ default: m.DeliveryMap })));

// Le livreur fait progresser sa course jusqu'à « colis récupéré ». La remise
// finale (« livré ») est validée par le CLIENT avec le code OTP remis en main
// propre (page « Confirmer la livraison »), jamais par le livreur.
const NEXT_STATUS: Partial<Record<DeliveryStatus, DeliveryStatus>> = {
  assigned: "picked_up",
};

const NEXT_LABEL: Partial<Record<DeliveryStatus, string>> = {
  assigned: "Marquer « colis récupéré »",
};

export default function DriverDeliveryPage() {
  const [searchParams] = useSearchParams();
  const deliveryId = searchParams.get("delivery");
  const [updating, setUpdating] = useState(false);
  const [sharingPosition, setSharingPosition] = useState(false);
  const [autoTracking, setAutoTracking] = useState(false);
  const [positionMessage, setPositionMessage] = useState<string | null>(null);
  const [confirmationCode, setConfirmationCode] = useState<string | null>(null);
  const [codeMessage, setCodeMessage] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [copied, setCopied] = useState(false);
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
    setCodeMessage(null);
    try {
      const response = await ordersApi.updateDeliveryStatus(deliveryId, next);
      setConfirmationCode(response.confirmation_code ?? null);
      if (response.confirmation_code) {
        setCodeMessage("Colis récupéré : communiquez ce code au client. Le code n'est affiché qu'une seule fois !");
      }
      setCopied(false);
      refetch();
    } catch (err) {
      setCodeMessage(err instanceof ApiError ? String((err.data as Record<string, unknown>).detail ?? err.message) : "Impossible de mettre à jour la course.");
    } finally {
      setUpdating(false);
    }
  }

  async function regenerateCode() {
    if (!deliveryId) return;
    setRegenerating(true);
    setCopied(false);
    try {
      const response = await ordersApi.regenerateDeliveryOtp(deliveryId);
      setConfirmationCode(response.confirmation_code);
      setCodeMessage("Nouveau code généré : l'ancien est désormais invalide.");
      refetch();
    } catch (err) {
      setCodeMessage(err instanceof ApiError ? String((err.data as Record<string, unknown>).detail ?? err.message) : "Impossible de régénérer le code.");
    } finally {
      setRegenerating(false);
    }
  }

  async function copyCode() {
    if (!confirmationCode) return;
    try {
      await navigator.clipboard.writeText(confirmationCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCodeMessage("Impossible de copier le code automatiquement.");
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

        {delivery.status === "picked_up" && (
          <div className="flex flex-col gap-3 rounded-lg border border-accent bg-muted/40 p-3">
            <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
              <KeyRound className="h-4 w-4 text-orange" />
              Code de confirmation à remettre au client
            </div>
            {confirmationCode ? (
              <div className="flex items-center justify-between gap-3">
                <span className="rounded-lg border border-dashed border-border bg-white px-4 py-2.5 font-mono text-2xl font-bold tracking-[0.35em] text-ink">
                  {confirmationCode}
                </span>
                <Button variant="secondary" size="sm" onClick={copyCode}>
                  <Copy className="h-4 w-4" />
                  {copied ? "Copié !" : "Copier"}
                </Button>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                Le code a été affiché à la récupération du colis et n'est pas ré-envoyé par sécurité. Récupérez-le depuis l'historique
                de cet écran ou régénérez-le.
              </p>
            )}
            <Button variant="secondary" size="sm" onClick={regenerateCode} loading={regenerating} className="w-fit">
              <RotateCcw className="h-4 w-4" />
              Régénérer un nouveau code (invalide l'ancien)
            </Button>
            {codeMessage && <p className="text-xs font-medium text-muted-foreground">{codeMessage}</p>}
          </div>
        )}

        {next ? (
          <Button onClick={advanceStatus} loading={updating}>
            {NEXT_LABEL[delivery.status]}
          </Button>
        ) : (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            {delivery.status === "delivered" && <CheckCircle2 className="h-4 w-4 text-success" />}
            {delivery.status === "delivered" ? "Course terminée : le client a confirmé la réception." : "En attente d'affectation par le commerçant."}
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