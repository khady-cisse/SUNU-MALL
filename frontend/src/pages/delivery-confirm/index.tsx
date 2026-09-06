import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, KeyRound, PackageCheck, PackageSearch } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError } from "@/lib/api";

export default function DeliveryConfirmPage() {
  const [searchParams] = useSearchParams();
  const orderId = searchParams.get("order");
  const { data: order, loading, refetch } = useAsync(
    () => (orderId ? ordersApi.getOrder(orderId) : Promise.resolve(null)),
    [orderId],
  );
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  if (!orderId) return <EmptyState icon={PackageSearch} title="Aucune commande sélectionnée" />;
  if (loading) return <Spinner label="Chargement…" />;
  if (!order) return <EmptyState icon={PackageSearch} title="Commande introuvable" />;

  const delivery = order.delivery;
  const delivered = delivery?.status === "delivered" || !!delivery?.delivered_at || confirmed;

  async function handleConfirm(e: React.FormEvent) {
    e.preventDefault();
    if (!delivery || code.length !== 6) return;
    setSubmitting(true);
    setError(null);
    try {
      await ordersApi.confirmDelivery(delivery.id, code);
      setConfirmed(true);
      setCode("");
      refetch();
    } catch (err) {
      if (err instanceof ApiError && typeof err.data === "object" && err.data && "detail" in err.data) {
        setError(String((err.data as Record<string, unknown>).detail));
      } else {
        setError("Impossible de confirmer la livraison. Vérifiez votre connexion.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="flex flex-col items-center gap-4 py-10 text-center">
      <span className={`grid h-16 w-16 place-items-center rounded-full ${delivered ? "bg-green-100" : "bg-accent"}`}>
        {delivered ? <CheckCircle2 className="h-9 w-9 text-success" /> : <PackageCheck className="h-9 w-9 text-orange" />}
      </span>
      <h1 className="font-display text-xl font-bold text-ink">Confirmation de livraison</h1>
      <p className="text-sm text-muted-foreground">
        Commande n°{order.id.slice(0, 8)} — statut actuel : <strong className="text-ink">{delivery?.status ?? "inconnu"}</strong>
      </p>

      {delivered ? (
        <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-green-50 px-4 py-2.5 text-sm font-semibold text-success">
          <CheckCircle2 className="h-4 w-4" /> Réception déjà confirmée. Bonne réception !
        </div>
      ) : delivery?.status === "picked_up" ? (
        <form onSubmit={handleConfirm} className="flex w-full max-w-sm flex-col gap-3">
          <label className="flex flex-col items-center gap-1.5 text-sm font-semibold text-ink">
            <KeyRound className="h-5 w-5 text-orange" />
            Code de confirmation remis par le livreur
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              placeholder="123456"
              className="focus-ring mt-1 w-40 rounded-lg border border-border px-3 py-2.5 text-center font-mono text-2xl font-bold tracking-[0.3em] text-ink"
            />
          </label>
          <Button type="submit" disabled={code.length !== 6} loading={submitting} className="w-full">
            Confirmer la réception
          </Button>
          {error && (
            <p role="alert" className="text-xs font-medium text-danger">
              {error}
            </p>
          )}
        </form>
      ) : (
        <p className="max-w-sm text-xs text-muted-foreground">
          Ce colis n'est pas encore en cours de livraison. La confirmation est possible dès que le livreur l'a récupéré
          (statut « colis récupéré »).
        </p>
      )}

      {!delivered && delivery?.status === "picked_up" && (
        <p className="max-w-sm text-xs text-muted-foreground">
          Le livreur vous a communiqué un code à 6 chiffres lors de la remise. Saisissez-le pour valider votre commande.
        </p>
      )}
    </Card>
  );
}