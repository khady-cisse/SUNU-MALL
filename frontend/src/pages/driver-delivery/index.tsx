import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AlertTriangle, CheckCircle2, Copy, KeyRound, MapPin, Navigation,
  PackageSearch, PackageX, RotateCcw, Satellite, Store, ThumbsDown, ThumbsUp, Truck, XCircle,
} from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import { apiErrorMessage, ApiError } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatDate } from "@/lib/utils";
import { DELIVERY_FAILURE_REASONS, DELIVERY_RETURN_REASONS, deliveryStatusLabel } from "@/lib/delivery";
import type { DeliveryStatus } from "@/types";

const DeliveryMap = lazy(() => import("@/components/marketplace/DeliveryMap").then((m) => ({ default: m.DeliveryMap })));

// Chaîne 2025 (spec §5) : assigned → accepté → en route vers la boutique →
// colis récupéré → en transit → en livraison. La remise finale (« livré »)
// est validée par le CLIENT avec le code OTP remis en main propre (page
// « Confirmer la livraison »), jamais par le livreur. Le refus, l'échec et le
// retour passent par leurs actions dédiées.
const NEXT_STATUS: Partial<Record<DeliveryStatus, DeliveryStatus>> = {
  accepted: "pickup_pending",
  pickup_pending: "picked_up",
  picked_up: "in_transit",
  in_transit: "out_for_delivery",
};

const NEXT_LABEL: Partial<Record<DeliveryStatus, string>> = {
  accepted: "Marquer « en route vers la boutique »",
  pickup_pending: "Marquer « colis récupéré »",
  picked_up: "Marquer « en transit »",
  in_transit: "Marquer « en livraison »",
};

const TERMINAL = new Set(["delivered", "delivery_failed", "customer_unavailable", "returned", "cancelled"]);
const FAIL_FAILABLE = new Set(["picked_up", "in_transit", "out_for_delivery"]);

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
  const [panel, setPanel] = useState<"refuse" | "fail" | "return" | null>(null);
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);
  const lastSentAt = useRef(0);

  const { data: delivery, loading: loadingDelivery, refetch } = useAsync(
    () => (deliveryId ? ordersApi.getDelivery(deliveryId) : Promise.resolve(null)),
    [deliveryId],
  );
  const { data: order, loading: loadingOrder } = useAsync(
    () => (delivery?.order ? ordersApi.getOrder(delivery.order) : Promise.resolve(null)),
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

  async function acceptMission() {
    if (!deliveryId) return;
    setActing(true);
    setActionError(null);
    try {
      await ordersApi.acceptDelivery(deliveryId);
      refetch();
    } catch (err) {
      setActionError(apiErrorMessage(err, "Impossible d'accepter la mission."));
    } finally {
      setActing(false);
    }
  }

  async function submitPanel(kind: "refuse" | "fail" | "return") {
    if (!deliveryId || !reason) {
      setActionError("Choisissez un motif.");
      return;
    }
    setActing(true);
    setActionError(null);
    try {
      if (kind === "refuse") await ordersApi.refuseDelivery(deliveryId, reason, comment);
      if (kind === "fail") await ordersApi.failDelivery(deliveryId, reason, comment);
      if (kind === "return") await ordersApi.requestDeliveryReturn(deliveryId, reason, comment);
      setPanel(null);
      setReason("");
      setComment("");
      refetch();
    } catch (err) {
      setActionError(apiErrorMessage(err, "L'action a échoué."));
    } finally {
      setActing(false);
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
  const pickup =
    order?.store_latitude != null && order?.store_longitude != null
      ? {
          lat: parseFloat(order.store_latitude),
          lng: parseFloat(order.store_longitude),
          label: "Boutique — point de départ",
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

  const refusePanel = panel === "refuse";
  const failPanel = panel === "fail";
  const returnPanel = panel === "return";
  const reasonOptions = Object.entries(
    panel === "return" ? DELIVERY_RETURN_REASONS : DELIVERY_FAILURE_REASONS,
  );

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
            <div className="flex flex-col gap-1 text-sm text-ink">
              <div className="flex items-center gap-2">
                <Store className="h-4 w-4 shrink-0 text-success" />
                <span>
                  Départ : {order.store_name}
                  {order.store_address || order.store_city ? ` — ${[order.store_address, order.store_city].filter(Boolean).join(", ")}` : ""}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <MapPin className="h-4 w-4 shrink-0 text-orange" />
                <span>
                  {order.address_detail?.street || "Adresse de livraison"}
                  {order.address_detail?.city ? `, ${order.address_detail.city}` : ""}
                </span>
              </div>
            </div>
            <p className="text-sm font-bold text-orange">{order.total_amount}</p>
          </>
        )}

        {driverPosition || pickup || destination ? (
          <Suspense fallback={<div className="h-56 w-full animate-pulse rounded-2xl bg-muted" />}>
            <DeliveryMap driverPosition={driverPosition} pickup={pickup} destination={destination} className="h-56 w-full" />
          </Suspense>
        ) : (
          <div className="rounded-lg border border-dashed border-border bg-muted/40 px-3 py-4 text-center text-xs text-muted-foreground">
            Aucune position à afficher pour l'instant. Partagez votre position pour l'afficher sur la carte.
          </div>
        )}

        <p className="border-t border-border pt-3 text-sm">
          Statut actuel : <strong className="text-ink">{deliveryStatusLabel(delivery.status)}</strong>
        </p>

        {delivery.status === "assigned" && (
          <div className="flex flex-col gap-2 rounded-lg border border-accent bg-muted/40 p-3">
            <p className="text-sm text-muted-foreground">
              Une mission vous est assignée. Acceptez-la pour prendre le relais, ou refusez-la avec un motif.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button onClick={acceptMission} loading={acting}>
                <ThumbsUp className="h-4 w-4" />
                Accepter la mission
              </Button>
              <Button variant="secondary" onClick={() => setPanel(refusePanel ? null : "refuse")}>
                <ThumbsDown className="h-4 w-4" />
                Refuser la mission
              </Button>
            </div>
            {refusePanel && (
              <div className="flex flex-col gap-3 border-t border-border pt-3">
                <label className="flex flex-col gap-1.5">
                  <span className="text-sm font-medium text-ink">Motif du refus</span>
                  <select
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    className="focus-ring w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink"
                  >
                    <option value="">Sélectionnez un motif…</option>
                    {Object.entries(DELIVERY_FAILURE_REASONS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <input
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Commentaire (facultatif)"
                  className="focus-ring w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink"
                />
                {actionError && <p className="text-xs text-danger">{actionError}</p>}
                <div className="flex gap-2">
                  <Button size="sm" variant="danger" onClick={() => submitPanel("refuse")} loading={acting}>
                    Confirmer le refus
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setPanel(null)}>
                    Annuler
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

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
                Le code a été affiché à la récupération du colis et n'est pas ré-envoyé par sécurité. Récupérez-le depuis
                l'historique de cet écran ou régénérez-le.
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
            {delivery.status === "delivered"
              ? "Course terminée : le client a confirmé la réception."
              : delivery.status === "pending"
                ? "En attente d'affectation par le commerçant."
                : TERMINAL.has(delivery.status)
                  ? "Course terminée."
                  : ""}
          </p>
        )}

        {FAIL_FAILABLE.has(delivery.status) && (
          <>
            <div className="flex flex-wrap gap-2 border-t border-border pt-3">
              <Button variant="secondary" onClick={() => setPanel(failPanel ? null : "fail")}>
                <XCircle className="h-4 w-4" />
                Signaler un échec
              </Button>
              <Button variant="secondary" onClick={() => setPanel(returnPanel ? null : "return")}>
                <PackageX className="h-4 w-4" />
                Demander le retour du colis
              </Button>
            </div>

            {failPanel && (
              <div className="flex flex-col gap-3 rounded-lg border border-danger/30 bg-red-50 p-3">
                <label className="flex flex-col gap-1.5">
                  <span className="text-sm font-medium text-ink">Motif de l'échec</span>
                  <select
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    className="focus-ring w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink"
                  >
                    <option value="">Sélectionnez un motif…</option>
                    {reasonOptions.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <input
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Détails (obligatoire pour un échec)"
                  className="focus-ring w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink"
                />
                {actionError && <p className="text-xs text-danger">{actionError}</p>}
                <div className="flex gap-2">
                  <Button size="sm" variant="danger" onClick={() => submitPanel("fail")} loading={acting}>
                    <AlertTriangle className="h-4 w-4" />
                    Confirmer l'échec
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setPanel(null)}>
                    Annuler
                  </Button>
                </div>
              </div>
            )}

            {returnPanel && (
              <div className="flex flex-col gap-3 rounded-lg border border-warning/30 bg-amber-50 p-3">
                <label className="flex flex-col gap-1.5">
                  <span className="text-sm font-medium text-ink">Motif du retour</span>
                  <select
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    className="focus-ring w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink"
                  >
                    <option value="">Sélectionnez un motif…</option>
                    {reasonOptions.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <input
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Commentaire (facultatif)"
                  className="focus-ring w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink"
                />
                {actionError && <p className="text-xs text-danger">{actionError}</p>}
                <div className="flex gap-2">
                  <Button size="sm" variant="danger" onClick={() => submitPanel("return")} loading={acting}>
                    <PackageX className="h-4 w-4" />
                    Confirmer la demande de retour
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setPanel(null)}>
                    Annuler
                  </Button>
                </div>
              </div>
            )}
          </>
        )}

        {actionError && !failPanel && !returnPanel && !refusePanel && (
          <p className="text-sm text-danger">{actionError}</p>
        )}

        {(delivery.status === "assigned" ||
          delivery.status === "accepted" ||
          delivery.status === "pickup_pending" ||
          delivery.status === "picked_up" ||
          delivery.status === "in_transit" ||
          delivery.status === "out_for_delivery") && (
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