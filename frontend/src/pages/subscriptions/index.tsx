import { useState } from "react";
import { Check, History as HistoryIcon, CreditCard, Crown, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { useAsync } from "@/hooks/useAsync";
import * as monetizationApi from "@/api/monetization";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PaymentModal } from "@/components/merchant/PaymentModal";
import { SubscriptionStatusCard } from "@/components/merchant/SubscriptionStatusCard";
import { Spinner } from "@/components/ui/Spinner";
import {
  billingCycleSuffix,
  formatDateShort,
  planLabel,
  SUBSCRIPTION_ACTION_LABEL,
} from "@/lib/subscriptions";
import { formatPrice } from "@/lib/utils";
import type { SubscriptionPlan } from "@/types";

const PLAN_ORDER: Record<string, number> = { STARTER: 0, PRO: 1, BUSINESS: 2 };

export default function SubscriptionsPage() {
  const { data: plans, loading: loadingPlans } = useAsync(() => monetizationApi.listSubscriptionPlans(), []);
  const { data: subscriptions, loading: loadingSubs, refetch } = useAsync(() => monetizationApi.listSubscriptions(), []);
  const { data: account, loading: loadingAccount, refetch: refetchAccount } = useAsync(
    () => monetizationApi.getMySubscriptionState(),
    [],
  );
  const { data: history, loading: loadingHistory, refetch: refetchHistory } = useAsync(
    () => monetizationApi.listSubscriptionHistory(),
    [],
  );
  const { data: payments, refetch: refetchPayments } = useAsync(
    () => monetizationApi.listSubscriptionPayments(),
    [],
  );

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [renewModal, setRenewModal] = useState(false);
  const [changePlanTarget, setChangePlanTarget] = useState<SubscriptionPlan | null>(null);

  const activeType = subscriptions?.find((s) => s.status === "active");
  const activePlan = plans?.find((p) => p.id === activeType?.plan);

  async function refetchAll() {
    refetch();
    refetchAccount();
    refetchHistory();
    refetchPayments();
  }

  function announce(message: string) {
    setError(null);
    setSuccess(message);
  }

  async function cancel() {
    if (!activeType) return;
    if (!confirm("Annuler votre abonnement ? Vous perdrez vos avantages à la fin de la période de grâce.")) return;
    setBusy("cancel");
    setError(null);
    setSuccess(null);
    try {
      await monetizationApi.cancelSubscription(activeType.id);
      announce("Votre abonnement a été annulé.");
      await refetchAll();
    } finally {
      setBusy(null);
    }
  }

  const loading = loadingPlans || loadingSubs || loadingAccount || loadingHistory;
  if (loading) return <Spinner label="Chargement de votre abonnement…" />;

  const otherPlans = [...(plans ?? [])]
    .filter((p) => p.is_active && p.code !== activePlan?.code)
    .sort((a, b) => (PLAN_ORDER[a.code] ?? 99) - (PLAN_ORDER[b.code] ?? 99));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
          <Crown className="h-6 w-6 text-orange" /> Mon abonnement
        </h1>
        <Link to="/offers">
          <Button variant="secondary">Découvrir nos offres</Button>
        </Link>
      </div>

      {success && (
        <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3.5 py-2.5 text-sm text-green-700">
          <Check className="h-4 w-4 shrink-0" />
          {success}
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
          <TriangleAlert className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {!activeType && !account?.has_active_subscription ? (
        <Card>
          <EmptyState
            icon={Crown}
            title="Vous n'avez pas encore d'abonnement"
            description="Souscrivez à une formule pour publier des produits et recevoir des commandes. Premier mois gratuit sur toutes les formules."
            action={
              <Link to="/offers">
                <Button>Voir nos offres</Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          <SubscriptionStatusCard
            account={account}
            onRenew={activeType?.status === "active" ? () => setRenewModal(true) : undefined}
            onChangePlan={activePlan ? () => setChangePlanTarget(activePlan) : undefined}
            onCancel={activeType?.status === "active" ? cancel : undefined}
          />

          {otherPlans.length > 0 && activePlan && (
            <Card>
              <CardTitle>Changer de formule</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                Montez ou descendez quand vous voulez — le changement s'applique après confirmation du paiement, et vos produits ne sont jamais supprimés.
              </p>
              <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {otherPlans.map((plan) => (
                  <Button
                    key={plan.id}
                    variant="secondary"
                    onClick={() => setChangePlanTarget(plan)}
                    className="justify-between"
                    loading={busy === `change-${plan.code}`}
                  >
                    <span>
                      Passer à {planLabel(plan.name)} · {formatPrice(plan.price)}
                      {billingCycleSuffix(plan.billing_cycle)}
                    </span>
                  </Button>
                ))}
              </div>
            </Card>
          )}
        </>
      )}

      <Card>
        <CardTitle className="flex items-center gap-2">
          <HistoryIcon className="h-4 w-4 text-muted-foreground" /> Historique de l'abonnement
        </CardTitle>
        {history?.length === 0 ? (
          <div className="mt-3">
            <EmptyState icon={HistoryIcon} title="Aucun événement enregistré" description="Les activations, renouvellements et changements de formule apparaîtront ici (jamais supprimés)." />
          </div>
        ) : (
          <div className="mt-3 flex flex-col gap-2">
            {history?.map((entry) => (
              <div key={entry.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-border py-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{formatDateShort(entry.created_at)}</span>
                  <Badge variant={entry.action === "expired" || entry.action === "cancelled" || entry.action === "suspended" ? "warning" : "default"}>
                    {SUBSCRIPTION_ACTION_LABEL[entry.action] ?? entry.action}
                  </Badge>
                  {entry.new_plan_name && <span className="font-medium text-ink">{planLabel(entry.new_plan_name)}</span>}
                  {entry.old_plan_name && entry.old_plan_name !== entry.new_plan_name && (
                    <span className="text-muted-foreground">← {planLabel(entry.old_plan_name)}</span>
                  )}
                </div>
                {entry.new_end_date && <span className="text-xs text-muted-foreground">jusqu'au {formatDateShort(entry.new_end_date)}</span>}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <CardTitle className="flex items-center gap-2">
          <CreditCard className="h-4 w-4 text-muted-foreground" /> Paiements
        </CardTitle>
        {payments?.length === 0 ? (
          <div className="mt-3">
            <EmptyState icon={CreditCard} title="Aucun paiement" description="Vos paiements d'abonnement (souscription, renouvellement, changement) apparaîtront ici." />
          </div>
        ) : (
          <div className="mt-3 flex flex-col gap-2">
            {payments?.map((payment) => (
              <div key={payment.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-border py-3 text-sm">
                <span className="text-muted-foreground">{formatDateShort(payment.created_at)}</span>
                <span className="font-mono text-xs text-muted-foreground">{payment.method}</span>
                <Badge variant={payment.status === "success" ? "success" : payment.status === "pending" ? "warning" : "danger"}>
                  {payment.status}
                </Badge>
                <span className="font-bold text-ink">{formatPrice(payment.amount)}</span>
              </div>
            ))}
          </div>
        )}
      </Card>

      {renewModal && account?.subscription && (
        <PaymentModal
          title={`Renouveler — ${planLabel(account.subscription.plan_name)}`}
          amount={account.subscription.price}
          periodLabel={account.subscription.billing_cycle ? billingCycleSuffix(account.subscription.billing_cycle) : undefined}
          createPayment={(method) => monetizationApi.renewSubscription(method)}
          onClose={() => setRenewModal(false)}
          onSuccess={() => {
            announce("Votre abonnement a été renouvelé. Un e-mail de confirmation vous a été envoyé.");
            void refetchAll();
          }}
        />
      )}

      {changePlanTarget && (
        <PaymentModal
          title={`Changer de formule — ${planLabel(changePlanTarget.name)}`}
          amount={changePlanTarget.price}
          periodLabel={billingCycleSuffix(changePlanTarget.billing_cycle)}
          createPayment={(method) => monetizationApi.changePlan(changePlanTarget.code, method)}
          onClose={() => setChangePlanTarget(null)}
          onSuccess={() => {
            announce(`Votre abonnement est désormais « ${planLabel(changePlanTarget.name)} ».`);
            void refetchAll();
          }}
        />
      )}
    </div>
  );
}