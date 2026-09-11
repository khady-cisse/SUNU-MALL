import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, KeyRound, PackageX } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import * as authApi from "@/api/auth";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { useAuthStore } from "@/store/authStore";
import { ApiError } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import type { GlobalOrder, Order } from "@/types";

function SetPasswordPrompt() {
  const updateUser = useAuthStore((s) => s.updateUser);
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 8) {
      setError("8 caractères minimum.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await authApi.setPassword(password);
      updateUser({ has_password: true });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? "Impossible d'enregistrer ce mot de passe." : "Impossible de contacter le serveur.");
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <Card className="flex items-center gap-3 border-green-200 bg-green-50">
        <CheckCircle2 className="h-5 w-5 shrink-0 text-success" />
        <p className="text-sm text-green-800">Compte créé ! Vous pourrez suivre vos commandes en vous connectant la prochaine fois.</p>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-3 text-left">
      <p className="flex items-center gap-2 font-semibold text-ink">
        <KeyRound className="h-4 w-4 text-orange" /> Créer un compte en un clic
      </p>
      <p className="text-sm text-muted-foreground">
        Définissez un mot de passe pour retrouver et suivre vos commandes la prochaine fois, sans ressaisir vos infos.
      </p>
      <form onSubmit={handleSubmit} className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <div className="flex-1">
          <Input
            type="password"
            placeholder="Mot de passe (8 caractères min.)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={error ?? undefined}
          />
        </div>
        <Button type="submit" loading={submitting} className="shrink-0">
          Créer mon compte
        </Button>
      </form>
    </Card>
  );
}

export default function OrderConfirmedPage() {
  const [searchParams] = useSearchParams();
  const orderId = searchParams.get("order");
  const globalOrderId = searchParams.get("gorder");
  const user = useAuthStore((s) => s.user);
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
        Commande n°{summary.id.slice(0, 8)} — <strong className="text-ink">{summary.storeName}</strong> -{" "}
        <strong className="text-orange">{formatPrice(summary.total)}</strong>
      </p>
      <div className="flex gap-3">
        {!isGlobal && (
          <Link to={`/tracking?order=${summary.id}`}>
            <Button>Suivre ma livraison</Button>
          </Link>
        )}
        <Link to="/orders">
          <Button variant="secondary">Voir mes commandes</Button>
        </Link>
      </div>

      {user && !user.has_password && (
        <div className="mt-2 w-full max-w-md">
          <SetPasswordPrompt />
        </div>
      )}
    </div>
  );
}
