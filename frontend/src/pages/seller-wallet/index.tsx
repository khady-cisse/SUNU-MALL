import { type ComponentType } from "react";
import { Link } from "react-router-dom";
import {
  ArrowDownToLine, Clock, Landmark, TrendingUp, Wallet as WalletIcon,
} from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as commissionsApi from "@/api/commissions";
import { Card, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatDate, formatPrice } from "@/lib/utils";

const SUBSCRIPTION_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  active: "success",
  trial: "default",
  expired: "danger",
  cancelled: "danger",
};

const SUBSCRIPTION_LABEL: Record<string, string> = {
  active: "Abonnement actif",
  trial: "Période d'essai",
  expired: "Abonnement expiré",
  cancelled: "Abonnement annulé",
};

const TX_TYPE_LABEL: Record<string, string> = {
  sale: "Vente",
  commission: "Commission",
  refund: "Remboursement",
  payout: "Retrait",
  release: "Libération",
  adjustment: "Ajustement",
};

export default function SellerWalletPage() {
  const { data, loading, error, refetch } = useAsync(() => commissionsApi.getSellerFinanceDashboard(), []);

  if (loading) return <Spinner label="Chargement du portefeuille…" />;
  if (error) return <ErrorState fullPage onRetry={refetch} />;
  if (!data) return null;

  const { wallet, subscription, recent_sales: sales, recent_wallet_transactions: tx } = data;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 font-display text-2xl font-bold text-ink">
          <WalletIcon className="h-6 w-6 text-orange" /> Mon portefeuille
        </h1>
        <div className="flex items-center gap-2">
          {subscription.plan && <Badge variant="default">{subscription.plan}</Badge>}
          <Badge variant={SUBSCRIPTION_VARIANT[subscription.status]}>{SUBSCRIPTION_LABEL[subscription.status]}</Badge>
        </div>
      </div>

      {!subscription.can_sell && (
        <Card className="flex flex-col gap-2 bg-amber-50/60 border-amber-200">
          <p className="font-semibold text-amber-800">Votre abonnement a expiré</p>
          <p className="text-sm text-amber-700">
            Vous ne pouvez plus recevoir de nouvelles commandes tant que vous n'avez pas souscrit à un plan.
            Vos données et votre historique financier sont conservés.
          </p>
        </Card>
      )}

      {subscription.status === "trial" && subscription.trial_ends_at && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Clock className="h-3.5 w-3.5 shrink-0" />
          Période d'essai (0 % de commission) valable jusqu'au {formatDate(subscription.trial_ends_at)}.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={ArrowDownToLine}
          label="Solde disponible"
          value={wallet.available_balance}
          hint="Retirable (KYC vérifié requis)"
        />
        <StatCard
          icon={Clock}
          label="Solde en attente"
          value={wallet.pending_balance}
          hint="Libéré après livraison confirmée"
        />
        <StatCard
          icon={TrendingUp}
          label="Total gagné"
          value={wallet.total_earned}
          hint="Revenus bruts cumulés"
        />
        <StatCard
          icon={Landmark}
          label="Total retiré"
          value={wallet.total_withdrawn}
          hint="Cumul des retraits effectués"
        />
      </div>



      <Card className="bg-gradient-orange text-white">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm text-white/80">Votre taux de commission actuel</p>
            <p className="font-display text-3xl font-bold">{parseFloat(subscription.rate)} %</p>
          </div>
          <p className="max-w-sm text-sm text-white/80">
            Pour chaque vente, Sunu Mall prélève sa commission sur le montant brut. Vous recevez
            directement votre montant net : vente brute − commission.
          </p>
          <Link to="/merchant-payouts">
            <Button variant="secondary">Retirer des fonds</Button>
          </Link>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle>Ventes récentes</CardTitle>
          {sales.length === 0 ? (
            <EmptyState icon={WalletIcon} title="Aucune vente pour le moment" />
          ) : (
            <div className="mt-3 flex flex-col gap-3">
              {sales.map((sale) => (
                <div key={sale.id} className="flex flex-col gap-1 border-t border-border pt-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-ink">Commande n°{sale.order_number.slice(0, 8)}</span>
                    {sale.is_refunded ? (
                      <Badge variant="danger">Remboursée</Badge>
                    ) : sale.is_released ? (
                      <Badge variant="success">Libérée</Badge>
                    ) : (
                      <Badge variant="warning">En attente</Badge>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2 text-muted-foreground">
                    <span>{formatDate(sale.created_at)}</span>
                    <span className="text-xs">{sale.store_name}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 pt-1">
                    <span title="Vente brute">
                      <p className="text-xs text-muted-foreground">Brut</p>
                      <p className="font-medium text-ink">{formatPrice(sale.gross_amount)}</p>
                    </span>
                    <span title="Commission Sunu Mall">
                      <p className="text-xs text-muted-foreground">
                        Commission ({parseFloat(sale.commission_rate)} %)
                      </p>
                      <p className="font-medium text-danger">−{formatPrice(sale.commission_amount)}</p>
                    </span>
                    <span title="Votre revenu">
                      <p className="text-xs text-muted-foreground">Votre revenu</p>
                      <p className="font-medium text-success">{formatPrice(sale.seller_amount)}</p>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <CardTitle>Historique du portefeuille</CardTitle>
          {tx.length === 0 ? (
            <EmptyState icon={WalletIcon} title="Aucun mouvement" />
          ) : (
            <div className="mt-3 flex flex-col gap-3">
              {tx.map((line) => (
                <div key={line.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 text-sm">
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 font-medium text-ink">
                      <span className="truncate">{TX_TYPE_LABEL[line.type] ?? line.type}</span>
                      <span className="text-xs text-muted-foreground">{formatDate(line.created_at)}</span>
                    </p>
                    {line.description && (
                      <p className="truncate text-xs text-muted-foreground">{line.description}</p>
                    )}
                  </div>
                  <div className="text-right">
                    <p className={line.amount.startsWith("-") ? "font-semibold text-danger" : "font-semibold text-success"}>
                      {line.amount.startsWith("-") ? "" : "+"}
                      {formatPrice(line.amount)}
                    </p>
                    {line.type === "release" ? (
                      <p className="text-xs text-muted-foreground">disponible {formatPrice(line.available_after)}</p>
                    ) : (
                      <p className="text-xs text-muted-foreground">en attente {formatPrice(line.pending_after)}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <Card className="flex items-start gap-3">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent text-orange">
        <Icon className="h-5 w-5" />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <p className="font-display text-xl font-bold text-ink">{formatPrice(value)}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
    </Card>
  );
}
