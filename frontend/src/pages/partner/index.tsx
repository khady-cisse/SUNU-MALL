import { Link } from "react-router-dom";
import { ChevronRight, Clock, MapPin, PackageCheck, PackageX, Timer, Truck, Wallet, XCircle } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as partnerApi from "@/api/partner";
import { cn, formatDate, formatPrice } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { DELIVERY_STATUS_LABEL, DELIVERY_STATUS_VARIANT } from "@/lib/delivery";
import type { PartnerStatus } from "@/types";

const PARTNER_STATUS_LABEL: Record<PartnerStatus, string> = {
  active: "Active",
  inactive: "En attente d'activation",
  suspended: "Suspendue",
};

const PARTNER_STATUS_TONE: Record<PartnerStatus, string> = {
  active: "bg-success/10 text-success",
  inactive: "bg-warning/10 text-warning",
  suspended: "bg-danger/10 text-danger",
};

export default function PartnerDashboardPage() {
  const { data: profile, loading: loadingProfile } = useAsync(() => partnerApi.getPartnerProfile(), []);
  const { data: stats, loading: loadingStats } = useAsync(() => partnerApi.getPartnerStats(), []);
  const { data: deliveries, loading: loadingDeliveries } = useAsync(() => partnerApi.listPartnerDeliveries(), []);

  if (loadingProfile || loadingStats) return <Spinner label="Chargement de votre espace…" />;
  if (!profile) return <ErrorState fullPage />;

  const recent = deliveries?.slice(0, 6) ?? [];
  const active = deliveries?.filter(
    (d) => d.status !== "delivered" && d.status !== "delivery_failed" && d.status !== "customer_unavailable" && d.status !== "returned" && d.status !== "cancelled",
  ) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-bold text-gray-900">{profile.name}</h1>
          <p className="text-sm text-muted-foreground">
            {profile.city || "Adresse non renseignée"}
            {profile.contact_phone ? ` · ${profile.contact_phone}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn("rounded-full px-3 py-1 text-xs font-bold", PARTNER_STATUS_TONE[profile.status])}>
            {PARTNER_STATUS_LABEL[profile.status]}
          </span>
          <span className="rounded-full border border-border bg-white px-3 py-1 text-xs font-semibold text-ink">
            Score {profile.score}/100
          </span>
        </div>
      </div>

      {loadingStats || !stats ? (
        <Spinner label="Calcul des statistiques…" />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Livraisons ce mois"
              value={stats.deliveries_month}
              icon={<PackageCheck className="h-5 w-5" />}
              tone="orange"
              subtitle={`${stats.deliveries_in_progress} en cours`}
            />
            <StatCard
              label="Livré ce mois"
              value={stats.deliveries_delivered}
              icon={<PackageCheck className="h-5 w-5" />}
              tone="green"
              subtitle={`Taux de réussite ${stats.success_rate}%`}
            />
            <StatCard
              label="Revenus générés"
              value={formatPrice(stats.total_revenue)}
              icon={<Wallet className="h-5 w-5" />}
              tone="blue"
              subtitle={stats.unpaid_amount && stats.unpaid_amount !== "0" ? `Impays : ${formatPrice(stats.unpaid_amount)}` : "Aucun impayé"}
            />
            <StatCard
              label="Livreurs actifs"
              value={stats.active_drivers}
              icon={<Truck className="h-5 w-5" />}
              tone="purple"
              subtitle={`Délai moyen ${stats.avg_delay_minutes} min`}
            />
          </div>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Total livraisons" value={stats.deliveries_total} icon={<MapPin className="h-5 w-5" />} tone="orange" />
            <StatCard label="Échecs" value={stats.deliveries_failed} icon={<XCircle className="h-5 w-5" />} tone="red" />
            <StatCard label="Retours" value={stats.deliveries_returned} icon={<PackageX className="h-5 w-5" />} tone="gray" subtitle={`Taux de retour ${stats.return_rate}%`} />
            <StatCard label="Délai moyen" value={`${stats.avg_delay_minutes} min`} icon={<Timer className="h-5 w-5" />} tone="blue" />
          </div>
        </>
      )}

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-semibold text-ink">
            <Clock className="h-4 w-4 text-orange" /> Courses en cours
          </h2>
          <Link to="/partner-deliveries" className="flex items-center gap-1 text-sm font-semibold text-orange hover:underline">
            Tout voir <ChevronRight className="h-4 w-4" />
          </Link>
        </div>
        {loadingDeliveries ? (
          <Spinner label="Chargement des livraisons…" />
        ) : active.length === 0 ? (
          <EmptyState icon={MapPin} title="Aucune course en cours" description="Les nouvelles commandes assignées à votre entreprise apparaîtront ici." />
        ) : (
          <div className="flex flex-col gap-2">
            {active.map((delivery) => (
              <Link
                key={delivery.id}
                to={`/partner-delivery?delivery=${delivery.id}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5 transition-colors hover:border-orange/50 hover:bg-muted/40"
              >
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">
                    {delivery.reference || delivery.id.slice(0, 8)} · {formatDate(delivery.created_at)}
                  </p>
                  <p className="truncate text-sm font-semibold text-ink">
                    {delivery.driver_detail?.full_name || "Livreur non affecté"}
                  </p>
                </div>
                <Badge variant={DELIVERY_STATUS_VARIANT[delivery.status]}>{DELIVERY_STATUS_LABEL[delivery.status]}</Badge>
              </Link>
            ))}
          </div>
        )}
      </Card>

      {recent.length > 0 && (
        <Card>
          <h2 className="mb-3 font-semibold text-ink">Dernières livraisons</h2>
          <div className="flex flex-col gap-2">
            {recent.map((delivery) => (
              <Link
                key={delivery.id}
                to={`/partner-delivery?delivery=${delivery.id}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5 transition-colors hover:border-orange/50 hover:bg-muted/40"
              >
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">
                    {delivery.reference || delivery.id.slice(0, 8)} · {formatDate(delivery.created_at)}
                  </p>
                  <p className="truncate text-sm font-medium text-ink">Commande n°{delivery.order.slice(0, 8)}</p>
                </div>
                <Badge variant={DELIVERY_STATUS_VARIANT[delivery.status]}>{DELIVERY_STATUS_LABEL[delivery.status]}</Badge>
              </Link>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}