import { Clock, Crown, History, RefreshCcw, Repeat, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import type { SubscriptionState } from "@/api/monetization";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { cn, formatPrice } from "@/lib/utils";
import {
  billingCycleSuffix,
  formatDateOnly,
  planLabel,
} from "@/lib/subscriptions";

/**
 * Carte « Mon abonnement » : formule, dates, jours restants, période de grâce
 * et consommation de la limite produits. Réutilisée sur le tableau de bord
 * vendeur et la page Mon abonnement. Aucune logique de calcul ici : tout
 * provient de l'état calculé côté backend (subscription/me/).
 */
export function SubscriptionStatusCard({
  account,
  onRenew,
  onChangePlan,
  onCancel,
}: {
  account: SubscriptionState | null;
  onRenew?: () => void;
  onChangePlan?: () => void;
  onCancel?: () => void;
}) {
  const subscription = account?.subscription;
  if (!subscription) return null;

  const daysLeft = subscription.is_active ? subscription.days_left : 0;
  const expiringSoon = subscription.is_active && daysLeft <= 3;
  const inGrace = subscription.in_grace;

  return (
    <Card className="border-orange">
      {inGrace && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3.5 py-2.5 text-sm text-amber-800">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            Votre abonnement est échu. Vous pouvez encore vendre pendant la période de grâce de{" "}
            {account.grace_period_days} jours : renouvelez rapidement pour conserver tous vos avantages.
          </p>
        </div>
      )}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <Crown className="h-4 w-4 text-orange" />
            <h2 className="font-display text-lg font-bold text-ink">{planLabel(subscription.plan_name)}</h2>
            {subscription.status === "active" ? (
              <Badge variant="success">Abonnement actif</Badge>
            ) : (
              <Badge variant="warning">{subscription.status}</Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            {formatPrice(subscription.price)}
            {subscription.billing_cycle ? billingCycleSuffix(subscription.billing_cycle) : " / mois"}
            {parseFloat(subscription.price) > 0 && " · Commission 0 %"}
          </p>
        </div>

        {subscription.ends_at && (
          <div className="flex items-center gap-2 text-sm">
            <Clock className={cn("h-4 w-4", expiringSoon ? "text-danger" : "text-muted-foreground")} />
            <span className={cn("font-medium", expiringSoon ? "text-danger" : "text-muted-foreground")}>
              {subscription.is_active
                ? `Expire le ${formatDateOnly(subscription.ends_at)} · ${daysLeft} jour${daysLeft > 1 ? "s" : ""} restant${daysLeft > 1 ? "s" : ""}`
                : `Terminé le ${formatDateOnly(subscription.ends_at)}`}
            </span>
          </div>
        )}
      </div>

      {typeof account.product_count === "number" && (
        <div className="mt-4 border-t border-gray-100 pt-4">
          <p className="mb-2 text-sm text-muted-foreground">
            Produits utilisés :{" "}
            <span className="font-semibold text-ink">
              {account.product_count}
              {account.is_unlimited ? "" : ` / ${account.product_limit}`}
            </span>
            {!account.is_unlimited && account.products_remaining === 0 && (
              <span className="ml-2 text-xs font-medium text-danger">Limite atteinte</span>
            )}
          </p>
          {!account.is_unlimited && account.product_limit != null && (
            <progress
              className="h-2 w-full overflow-hidden rounded-full bg-accent [&::-webkit-progress-bar]:bg-accent [&::-webkit-progress-value]:rounded-full [&::-webkit-progress-value]:bg-orange"
              max={account.product_limit}
              value={Math.min(account.product_count, account.product_limit)}
            />
          )}
        </div>
      )}

      {(onRenew || onChangePlan || onCancel) && (
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-4">
          {onRenew && (
            <Button size="sm" onClick={onRenew}>
              <RefreshCcw className="h-4 w-4" /> Renouveler
            </Button>
          )}
          {onChangePlan && (
            <Button size="sm" variant="secondary" onClick={onChangePlan}>
              <Repeat className="h-4 w-4" /> Changer de formule
            </Button>
          )}
          {onCancel && (
            <Button size="sm" variant="danger" onClick={onCancel}>
              Annuler
            </Button>
          )}
          <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
            <History className="h-3.5 w-3.5" />
            <Link to="/subscriptions" className="transition-colors hover:text-orange">
              Voir mon historique
            </Link>
          </span>
        </div>
      )}
    </Card>
  );
}