import { type ComponentType, useState } from "react";
import { Banknote, CheckCircle2, Clock, Landmark, Layers, ReceiptText, TrendingUp, Wallet as WalletIcon, XCircle } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as commissionsApi from "@/api/commissions";
import { Card, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import { formatDate, formatPrice } from "@/lib/utils";

const PAGE_SIZE = 20;

const PLAN_LABEL: Record<string, string> = {
  BASIC: "Basic",
  PRO: "Pro",
  BUSINESS: "Business",
};

const PAYOUT_STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  pending: "warning",
  completed: "success",
  rejected: "danger",
};

function StatCard({
  icon: Icon,
  label,
  value,
  tone = "orange",
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
  tone?: "orange" | "green" | "blue" | "red";
}) {
  const tones: Record<string, string> = {
    orange: "bg-accent text-orange",
    green: "bg-green-50 text-green-700",
    blue: "bg-blue-50 text-blue-700",
    red: "bg-red-50 text-red-600",
  };
  return (
    <Card className="flex items-center gap-3">
      <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${tones[tone]}`}>
        <Icon className="h-5 w-5" />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <p className="truncate font-display text-xl font-bold text-ink">{value}</p>
      </div>
    </Card>
  );
}

function CommissionsTable() {
  const [page, setPage] = useState(1);
  const [plan, setPlan] = useState("");
  const { data: result, loading, error, refetch } = useAsync(
    () => commissionsApi.listCommissionTransactions({ page, plan: plan || undefined }),
    [page, plan],
  );

  const rows = result?.results ?? [];
  const totalPages = result ? Math.max(1, Math.ceil(result.count / PAGE_SIZE)) : 1;

  return (
    <Card>
      <CardTitle>Commissions Sunu Mall par vente</CardTitle>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <label className="text-xs font-medium text-muted-foreground">Plan</label>
        <select
          value={plan}
          onChange={(e) => {
            setPlan(e.target.value);
            setPage(1);
          }}
          className="focus-ring rounded-lg border border-border px-2.5 py-1.5 text-sm text-ink"
        >
          <option value="">Tous</option>
          <option value="BASIC">Basic</option>
          <option value="PRO">Pro</option>
          <option value="BUSINESS">Business</option>
          <option value="trial">Essai (trial)</option>
        </select>
      </div>

      {loading ? (
        <Spinner label="Chargement des commissions…" />
      ) : error ? (
        <ErrorState onRetry={refetch} />
      ) : rows.length === 0 ? (
        <EmptyState icon={ReceiptText} title="Aucune commission" />
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-2 py-2 font-bold">Commande</th>
                <th className="px-2 py-2 font-bold">Vendeur</th>
                <th className="px-2 py-2 font-bold">Plan</th>
                <th className="px-2 py-2 text-right font-bold">Brut</th>
                <th className="px-2 py-2 text-right font-bold">Taux</th>
                <th className="px-2 py-2 text-right font-bold">Commission</th>
                <th className="px-2 py-2 text-right font-bold">Net vendeur</th>
                <th className="px-2 py-2 font-bold">Statut</th>
                <th className="px-2 py-2 font-bold">Date</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-border/60 hover:bg-muted/40">
                  <td className="px-2 py-2.5 font-mono text-xs text-muted-foreground">#{row.order_number.slice(0, 8)}</td>
                  <td className="px-2 py-2.5 font-medium text-ink">{row.store_name}</td>
                  <td className="px-2 py-2.5">
                    {row.plan ? (
                      <Badge variant="default">{PLAN_LABEL[row.plan] ?? row.plan}</Badge>
                    ) : (
                      <Badge variant="default">Essai</Badge>
                    )}
                  </td>
                  <td className="px-2 py-2.5 text-right text-ink">{formatPrice(row.gross_amount)}</td>
                  <td className="px-2 py-2.5 text-right text-ink">{parseFloat(row.commission_rate)} %</td>
                  <td className="px-2 py-2.5 text-right font-medium text-danger">{formatPrice(row.commission_amount)}</td>
                  <td className="px-2 py-2.5 text-right font-medium text-success">{formatPrice(row.seller_amount)}</td>
                  <td className="px-2 py-2.5">
                    {row.is_refunded ? (
                      <Badge variant="danger">Remboursée</Badge>
                    ) : row.is_released ? (
                      <Badge variant="success">Libérée</Badge>
                    ) : (
                      <Badge variant="warning">En attente</Badge>
                    )}
                  </td>
                  <td className="px-2 py-2.5 text-xs text-muted-foreground">{formatDate(row.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination page={page} totalPages={totalPages} onPageChange={setPage} className="mt-4" />
    </Card>
  );
}

function PayoutsPanel() {
  const [page, setPage] = useState(1);
  const { data: result, loading, error, refetch } = useAsync(() => commissionsApi.listPayouts({ page }), [page]);
  const [busy, setBusy] = useState<{ id: string; action: "approve" | "reject" } | null>(null);

  async function handle(id: string, action: "approve" | "reject") {
    if (action === "approve" && !confirm("Confirmer que les fonds ont bien été transférés au vendeur ?")) return;
    if (action === "reject" && !confirm("Rejeter ce retrait ? Le montant sera recrédité au vendeur.")) return;
    setBusy({ id, action });
    try {
      if (action === "approve") await commissionsApi.approvePayout(id);
      else await commissionsApi.rejectPayout(id);
      refetch();
    } finally {
      setBusy(null);
    }
  }

  const payouts = result?.results ?? [];
  const totalPages = result ? Math.max(1, Math.ceil(result.count / PAGE_SIZE)) : 1;
  const pending = payouts.filter((p) => p.status === "pending");

  if (loading) return <Spinner label="Chargement des retraits…" />;
  if (error) return <ErrorState onRetry={refetch} />;
  if (payouts.length === 0) return null;

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <CardTitle>Retraits vendeurs</CardTitle>
        <Badge variant={pending.length ? "warning" : "success"}>{pending.length} en attente</Badge>
      </div>
      <div className="flex flex-col gap-3">
        {payouts.map((payout) => (
          <div key={payout.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 text-sm">
            <div>
              <p className="font-medium text-ink">{formatPrice(payout.amount)}</p>
              <p className="text-xs text-muted-foreground">
                Vendeur {payout.seller.slice(0, 8)} · {formatDate(payout.created_at)}
                {payout.reference ? ` · ${payout.reference}` : ""}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={PAYOUT_STATUS_VARIANT[payout.status]}>{payout.status}</Badge>
              {payout.status === "pending" && (
                <>
                  <Button
                    size="sm"
                    loading={busy?.id === payout.id && busy.action === "approve"}
                    onClick={() => handle(payout.id, "approve")}
                  >
                    <CheckCircle2 className="h-4 w-4" /> Approuver
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    loading={busy?.id === payout.id && busy.action === "reject"}
                    onClick={() => handle(payout.id, "reject")}
                  >
                    <XCircle className="h-4 w-4" /> Rejeter
                  </Button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
      <Pagination page={page} totalPages={totalPages} onPageChange={setPage} className="mt-4" />
    </Card>
  );
}

export default function AdminFinancePage() {
  const { data: stats, loading, error, refetch } = useAsync(() => commissionsApi.getCommissionStats(), []);

  if (loading) return <Spinner label="Chargement des statistiques financières…" />;
  if (error) return <ErrorState fullPage onRetry={refetch} />;
  if (!stats) return null;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="flex items-center gap-2 font-display text-2xl font-bold text-ink">
        <Banknote className="h-6 w-6 text-orange" /> Finance
      </h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={WalletIcon} label="Solde plateforme" value={formatPrice(stats.platform_balance)} />
        <StatCard icon={TrendingUp} label="Commission aujourd'hui" value={formatPrice(stats.today_commissions)} tone="green" />
        <StatCard icon={Layers} label="Commission ce mois" value={formatPrice(stats.month_commissions)} tone="blue" />
        <StatCard icon={ReceiptText} label="Commission totale" value={formatPrice(stats.total_commissions)} tone="red" />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard icon={Landmark} label="Volume total des ventes" value={formatPrice(stats.total_volume)} />
        <StatCard icon={Banknote} label="Montant reversé aux vendeurs" value={formatPrice(stats.total_to_sellers)} />
        <StatCard icon={Clock} label="Retraits complétés" value={formatPrice(stats.total_payouts)} />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <StatCard icon={ReceiptText} label="Abonnements reçus" value={formatPrice(stats.platform_total_subscriptions)} />
        <StatCard icon={XCircle} label="Commissions remboursées" value={formatPrice(stats.total_refunded_commissions)} tone="red" />
      </div>

      {stats.by_plan.length > 0 && (
        <Card>
          <CardTitle>Commissions par plan</CardTitle>
          <div className="mt-3 flex flex-col gap-2">
            {stats.by_plan.map((p) => (
              <div key={p.plan} className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 text-sm">
                <Badge variant="default">{PLAN_LABEL[p.plan] ?? (p.plan ? p.plan : "Essai")}</Badge>
                <span className="text-muted-foreground">{p.count} vente{p.count > 1 ? "s" : ""}</span>
                <span className="text-muted-foreground">Volume {formatPrice(p.volume)}</span>
                <span className="font-medium text-danger">{formatPrice(p.commissions)}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      <PayoutsPanel />
      <CommissionsTable />
    </div>
  );
}
