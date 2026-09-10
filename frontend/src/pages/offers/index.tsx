import { useState } from "react";
import { Check, Crown, Gift, Megaphone, Sparkles, X } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as monetizationApi from "@/api/monetization";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PaymentModal } from "@/components/merchant/PaymentModal";
import { Spinner } from "@/components/ui/Spinner";
import { cn, formatPrice } from "@/lib/utils";
import { billingCycleSuffix, planLabel, PLAN_BLURB, productLimitLabel } from "@/lib/subscriptions";
import type { SubscriptionPlan } from "@/types";

const PLAN_ORDER: Record<string, number> = { STARTER: 0, PRO: 1, BUSINESS: 2 };
const PLAN_SORT = (a: SubscriptionPlan, b: SubscriptionPlan) =>
  (PLAN_ORDER[a.code] ?? 99) - (PLAN_ORDER[b.code] ?? 99);

/** Libellé « paiements et livraison inclus », présent sur toutes les formules. */
const FEATURE_PAYMENTS = "Paiements client et livraison inclus";

export default function OffersPage() {
  const { data: plans, loading } = useAsync(() => monetizationApi.listSubscriptionPlans(), []);
  const { data: account, refetch } = useAsync(() => monetizationApi.getMySubscriptionState(), []);
  const [target, setTarget] = useState<SubscriptionPlan | null>(null);

  if (loading) return <Spinner label="Chargement des offres…" />;

  const available = [...(plans ?? [])].filter((p) => p.is_active).sort(PLAN_SORT);
  const activeCode = account?.subscription?.plan_code;

  const comparisonRows: { label: string; values: (plan: SubscriptionPlan) => string }[] = [
    { label: "Produits", values: (p) => productLimitLabel(p.max_products) },
    { label: "Commission Sunu Mall", values: () => "0 %" },
    { label: "Durée de la période", values: (p) => `${p.duration_days} jours` },
    { label: "Paiements et livraison", values: () => "Inclus" },
    { label: "Support", values: (p) => (p.features?.support as string) ?? "Standard" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-2">
        <Megaphone className="h-6 w-6 text-orange" />
        <div>
          <h1 className="font-display text-2xl font-bold text-gray-900">Nos offres</h1>
          <p className="text-sm text-muted-foreground">
            Lancement : commission Sunu Mall à 0 % sur toutes les formules. Premier mois gratuit.
          </p>
        </div>
      </div>

      {activeCode && (
        <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3.5 py-2.5 text-sm text-green-700">
          <Check className="h-4 w-4 shrink-0" />
          Vous êtes actuellement sur la formule <span className="font-semibold">{planLabel(activeCode)}</span>. Pour changer, utilisez la page « Mon abonnement ».
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {available.map((plan) => {
          const isActive = plan.code === activeCode;
          const recommended = plan.code === "PRO";
          const features = Object.values(plan.features ?? {}) as string[];
          return (
            <Card key={plan.id} className={cn("relative flex flex-col", isActive ? "border-orange ring-1 ring-orange" : recommended ? "border-orange/60" : "")}>
              {recommended && !isActive && (
                <span className="absolute right-4 top-4">
                  <Badge variant="sponsored">Recommandé</Badge>
                </span>
              )}
              {isActive && (
                <span className="absolute right-4 top-4">
                  <Badge variant="success">Votre formule</Badge>
                </span>
              )}
              <div className="mb-3 flex items-center gap-2">
                <h2 className="font-display text-lg font-bold text-ink">{planLabel(plan.name)}</h2>
              </div>
              <p className="mb-3 font-display text-3xl font-bold text-orange">
                {formatPrice(plan.price)}
                <span className="text-sm font-normal text-muted-foreground">{billingCycleSuffix(plan.billing_cycle)}</span>
              </p>
              {PLAN_BLURB[plan.code] && <p className="mb-3 text-sm text-muted-foreground">{PLAN_BLURB[plan.code]}</p>}
              <ul className="mb-5 flex flex-1 flex-col gap-1.5 text-sm text-muted-foreground">
                <li className="flex items-center gap-2">
                  <Check className="h-4 w-4 shrink-0 text-success" /> {productLimitLabel(plan.max_products)}
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-4 w-4 shrink-0 text-success" /> Commission Sunu Mall : 0 %
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-4 w-4 shrink-0 text-success" /> Période de {plan.duration_days} jours
                </li>
                {features.filter((f) => f !== FEATURE_PAYMENTS).map((f, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <Check className="h-4 w-4 shrink-0 text-success" /> {f}
                  </li>
                ))}
              </ul>
              <Gift className="mb-2 inline-flex h-4 w-4 text-orange" />
              <Button
                variant={isActive ? "secondary" : "primary"}
                disabled={isActive}
                onClick={() => setTarget(plan)}
                className="w-full"
              >
                {isActive ? "Formule actuelle" : `S'abonner · ${formatPrice(plan.price)}`}
              </Button>
            </Card>
          );
        })}
      </div>

      <Card>
        <h2 className="mb-1 flex items-center gap-2 font-display text-lg font-bold text-ink">
          <Sparkles className="h-5 w-5 text-orange" /> Comparer les formules
        </h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Valeurs pilotées par le backend — un prix ou une limite modifié par l'administration se reflète ici sans changement de code.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="pb-3 pr-4 font-semibold text-muted-foreground">Caractéristique</th>
                {available.map((plan) => (
                  <th key={plan.id} className={cn("pb-3 px-4 font-display", plan.code === activeCode ? "text-orange" : "text-ink")}>
                    {planLabel(plan.name)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map((row, idx) => (
                <tr key={row.label} className={cn("border-b border-border/60", idx % 2 ? "bg-muted/30" : "")}>
                  <td className="py-3 pr-4 font-medium text-ink">{row.label}</td>
                  {available.map((plan) => {
                    const value = row.values(plan);
                    return (
                      <td key={plan.id} className="px-4 py-3">
                        <span className={cn("inline-flex items-center gap-1.5 text-muted-foreground", row.label === "Produits" && "font-semibold text-ink")}>
                          {value === "Inclus" ? <Check className="h-4 w-4 text-success" /> : value === "Non" ? <X className="h-4 w-4 text-danger" /> : value}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td className="py-3 pr-4" />
                {available.map((plan) => (
                  <td key={plan.id} className="px-4 py-3">
                    <Button
                      size="sm"
                      variant={plan.code === activeCode ? "secondary" : "primary"}
                      disabled={plan.code === activeCode}
                      onClick={() => setTarget(plan)}
                      className="w-full"
                    >
                      {plan.code === activeCode ? "Formule actuelle" : formatPrice(plan.price) + billingCycleSuffix(plan.billing_cycle)}
                    </Button>
                  </td>
                ))}
              </tr>
            </tfoot>
          </table>
        </div>
        <p className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
          <Crown className="h-4 w-4 text-orange" />
          Premier mois offert sur toutes les formules à votre toute première souscription.
        </p>
      </Card>

      {target && (
        <PaymentModal
          title={`S'abonner — ${planLabel(target.name)}`}
          amount={target.price}
          periodLabel={billingCycleSuffix(target.billing_cycle)}
          createPayment={(method) =>
            monetizationApi.subscribe(target.id, method).then((r) => ({ payment: r.payment }))
          }
          onClose={() => setTarget(null)}
          onSuccess={() => {
            void refetch();
          }}
        />
      )}
    </div>
  );
}