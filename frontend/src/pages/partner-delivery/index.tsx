import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, Lightbulb, MapPin, PackageSearch, RefreshCw, Truck, User } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import * as partnerApi from "@/api/partner";
import { apiErrorMessage, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { DELIVERY_STATUS_LABEL, DELIVERY_STATUS_VARIANT, reasonLabel } from "@/lib/delivery";
import type { Driver } from "@/types";

const ACTION_LABEL: Record<string, string> = {
  created: "Livraison créée",
  assigned: "Livreur affecté",
  status_changed: "Changement de statut",
  delivery_failed: "Échec de livraison",
  return_requested: "Retour demandé",
  returned: "Colis retourné",
  cancelled: "Livraison annulée",
};

const ACTOR_ROLE_LABEL: Record<string, string> = {
  system: "Système",
  merchant: "Commerçant",
  driver: "Livreur",
  partner: "Partenaire",
  admin: "Administrateur",
  customer: "Client",
};

export default function PartnerDeliveryPage() {
  const [searchParams] = useSearchParams();
  const deliveryId = searchParams.get("delivery");

  const { data: delivery, loading, refetch } = useAsync(
    () => (deliveryId ? ordersApi.getDelivery(deliveryId) : Promise.resolve(null)),
    [deliveryId],
  );
  const { data: drivers } = useAsync(() => partnerApi.listCompanyDrivers(), []);

  const [suggesting, setSuggesting] = useState(false);
  const [suggested, setSuggested] = useState<Driver[] | null>(null);
  const [suggestMessage, setSuggestMessage] = useState<string | null>(null);
  const [assigningId, setAssigningId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setSuggested(null);
    setSuggestMessage(null);
    setActionError(null);
  }, [deliveryId]);

  if (!deliveryId) return <EmptyState icon={PackageSearch} title="Sélectionnez une livraison" />;
  const deliveryIdValue: string = deliveryId;
  if (loading) return <Spinner label="Chargement de la livraison…" />;
  if (!delivery) return <EmptyState icon={PackageSearch} title="Livraison introuvable" />;

  const assignable =
    delivery.status === "pending" || delivery.status === "assigned" || delivery.status === "return_requested";

  async function suggest() {
    setSuggesting(true);
    setSuggestMessage(null);
    setActionError(null);
    try {
      const result = await ordersApi.suggestDrivers(deliveryIdValue);
      if (result.drivers.length === 0) {
        setSuggestMessage("Aucun livreur disponible à proximité de la boutique pour le moment. Réessayez plus tard.");
        setSuggested([]);
      } else {
        setSuggested(result.drivers);
        if (result.message) setSuggestMessage(result.message);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setActionError(apiErrorMessage(err, "Impossible de proposer des livreurs."));
      } else {
        setActionError("Impossible de proposer des livreurs.");
      }
    } finally {
      setSuggesting(false);
    }
  }

  async function assign(driverId: string) {
    setAssigningId(driverId);
    setActionError(null);
    try {
      await ordersApi.assignDriver(deliveryIdValue, driverId);
      setSuggested(null);
      refetch();
    } catch (err) {
      if (err instanceof ApiError) {
        setActionError(apiErrorMessage(err, "Impossible d'affecter ce livreur."));
      } else {
        setActionError("Impossible d'affecter ce livreur.");
      }
    } finally {
      setAssigningId(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
          <Truck className="h-6 w-6 text-orange" /> Livraison {delivery.reference || delivery.id.slice(0, 8)}
        </h1>
        <div className="flex items-center gap-2">
          <Badge variant={DELIVERY_STATUS_VARIANT[delivery.status]}>{DELIVERY_STATUS_LABEL[delivery.status]}</Badge>
          <Button variant="secondary" size="sm" onClick={refetch}>
            <RefreshCw className="h-4 w-4" />
            Actualiser
          </Button>
        </div>
      </div>

      <Card className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          Commande n°{delivery.order.slice(0, 8)} · passée le {formatDate(delivery.created_at)}
          {delivery.picked_up_at ? ` · colis récupéré le ${formatDate(delivery.picked_up_at)}` : ""}
          {delivery.delivered_at ? ` · livrée le ${formatDate(delivery.delivered_at)}` : ""}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm">
            <User className="h-4 w-4 text-orange" />
            {delivery.driver_detail ? (
              <span>
                <strong className="text-ink">{delivery.driver_detail.full_name || delivery.driver_detail.email}</strong>{" "}
<span className="text-muted-foreground">
                      · {delivery.driver_detail.vehicle_type}
                      {delivery.driver_detail.distance_km != null ? ` · à ${delivery.driver_detail.distance_km} km de la boutique` : ""}
                    </span>
              </span>
            ) : (
              <span className="text-muted-foreground">Aucun livreur affecté</span>
            )}
          </div>
        </div>

        {delivery.failure_reason && (
          <p className="rounded-lg border border-danger/30 bg-red-50 px-3 py-2 text-sm text-danger">
            Échec : {reasonLabel(delivery.failure_reason)}
            {delivery.failure_comment ? ` — ${delivery.failure_comment}` : ""}
          </p>
        )}
        {delivery.return_reason && (
          <p className="rounded-lg border border-warning/30 bg-amber-50 px-3 py-2 text-sm text-amber-700">
            Retour ({reasonLabel(delivery.return_reason)})
          </p>
        )}
        {delivery.refuse_reason && (
          <p className="rounded-lg border border-warning/30 bg-amber-50 px-3 py-2 text-sm text-amber-700">
            Refus du livreur : {delivery.refuse_reason}
          </p>
        )}

        {actionError && <p className="rounded-lg border border-danger/30 bg-red-50 px-3 py-2 text-sm text-danger">{actionError}</p>}
      </Card>

      {assignable && (
        <Card className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 font-semibold text-ink">
              <Lightbulb className="h-4 w-4 text-orange" /> Affecter un livreur
            </h2>
            <Button variant="secondary" size="sm" onClick={suggest} loading={suggesting}>
              <Lightbulb className="h-4 w-4" />
              Proposer le meilleur livreur
            </Button>
          </div>

          {suggestMessage && <p className="text-sm text-muted-foreground">{suggestMessage}</p>}

          {suggested !== null && suggested.length > 0 && (
            <div className="flex flex-col gap-2">
              {suggested.map((driver) => (
                <div key={driver.id} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5">
                  <div>
                    <p className="font-semibold text-ink">{driver.full_name || driver.email}</p>
                    <p className="text-xs text-muted-foreground">
                      {driver.vehicle_type}
                      {driver.distance_km != null ? ` · à ${driver.distance_km} km de la boutique` : " · position inconnue"}
                    </p>
                  </div>
                  <Button size="sm" onClick={() => assign(driver.id)} loading={assigningId === driver.id}>
                    <CheckCircle2 className="h-4 w-4" />
                    Affecter
                  </Button>
                </div>
              ))}
            </div>
          )}

          {drivers && drivers.length > 0 && (
            <div className="flex flex-col gap-2">
              <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Livreurs de l'entreprise</p>
              {drivers
                .filter((d) => !d.is_suspended)
                .map((driver) => (
                  <div key={driver.id} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5">
                    <div>
                      <p className="font-semibold text-ink">{driver.full_name || driver.email}</p>
                      <p className="flex items-center gap-1 text-xs text-muted-foreground">
                        <MapPin className="h-3 w-3" />
                        {driver.availability_status === "available" ? "Disponible" : driver.availability_status === "busy" ? "En course" : "Hors ligne"}
                        {driver.last_position ? ` · position signalée le ${formatDate(driver.position_updated_at ?? "")}` : " · aucune position"}
                      </p>
                    </div>
                    <Button size="sm" variant="secondary" onClick={() => assign(driver.id)} loading={assigningId === driver.id}>
                      Affecter
                    </Button>
                  </div>
                ))}
            </div>
          )}

          {drivers && drivers.filter((d) => !d.is_suspended).length === 0 && suggestMessage === null && (
            <p className="text-sm text-muted-foreground">
              Aucun livreur actif dans l'entreprise. Ajoutez des livreurs depuis « Mes livreurs », puis demandez-leur de signaler leur position GPS.
            </p>
          )}
        </Card>
      )}

      <Card>
        <h2 className="mb-3 font-semibold text-ink">Historique de la livraison</h2>
        {delivery.timeline.length === 0 ? (
          <p className="text-sm text-muted-foreground">Aucun événement enregistré pour le moment.</p>
        ) : (
          <ol className="relative flex flex-col gap-4 pl-6 before:absolute before:left-2 before:top-1 before:h-full before:w-px before:bg-border">
            {[...delivery.timeline].reverse().map((event, index) => (
              <li key={index} className="relative">
                <span
                  className={`absolute -left-6 top-1 h-3 w-3 rounded-full border-2 border-white ${
                    event.new_status === "delivered" ? "bg-success" : "bg-orange"
                  }`}
                />
                <p className="text-sm font-semibold text-ink">
                  {ACTION_LABEL[event.action] ?? event.action}
                  {event.new_status ? ` → ${DELIVERY_STATUS_LABEL[event.new_status as keyof typeof DELIVERY_STATUS_LABEL] ?? event.new_status}` : ""}
                </p>
                <p className="text-xs text-muted-foreground">
                  {ACTOR_ROLE_LABEL[event.actor_role] ?? event.actor_role} · {formatDate(event.created_at)}
                  {event.comment ? ` — ${event.comment}` : ""}
                </p>
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}