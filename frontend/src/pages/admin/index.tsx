import { type ComponentType, useMemo } from "react";
import { ShieldCheck, Store as StoreIcon, Users } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as usersApi from "@/api/users";
import type { DailyCount } from "@/api/users";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { TrendChart } from "@/components/ui/TrendChart";

function toTrendPoints(daily: DailyCount[]) {
  return daily.map((d) => ({
    label: new Date(d.date).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" }),
    value: d.count,
  }));
}

export default function AdminDashboardPage() {
  const { data: stats, loading: loadingStats, error: statsError, refetch: refetchStats } = useAsync(() => usersApi.getDashboardStats(), []);

  const newUsersByDay = useMemo(() => toTrendPoints(stats?.trend.new_users ?? []), [stats]);
  const newStoresByDay = useMemo(() => toTrendPoints(stats?.trend.new_stores ?? []), [stats]);

  if (loadingStats) return <Spinner label="Chargement des statistiques…" />;
  if (statsError) return <ErrorState message="Impossible de charger les statistiques." onRetry={refetchStats} />;
  if (!stats) return null;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold text-gray-900">Tableau de bord administrateur</h1>

      <div>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-muted-foreground">
          <Users className="h-4 w-4" /> Utilisateurs
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Stat label="Total" value={stats.users.total} icon={Users} />
          <Stat label="Actifs" value={stats.users.active} icon={Users} />
          <Stat label="Non vérifiés" value={stats.users.unverified} icon={Users} />
        </div>
      </div>

      <div>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-muted-foreground">
          <StoreIcon className="h-4 w-4" /> Boutiques
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
          <Stat label="Total" value={stats.stores.total} icon={StoreIcon} />
          <Stat label="Actives" value={stats.stores.active} icon={StoreIcon} />
          <Stat label="En attente" value={stats.stores.pending_review} icon={StoreIcon} />
          <Stat label="Suspendues" value={stats.stores.suspended} icon={StoreIcon} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 flex items-center gap-2 font-semibold text-ink">
            <Users className="h-4 w-4 text-orange" /> Nouveaux utilisateurs (14 derniers jours)
          </h2>
          <TrendChart data={newUsersByDay} />
        </Card>
        <Card>
          <h2 className="mb-4 flex items-center gap-2 font-semibold text-ink">
            <StoreIcon className="h-4 w-4 text-orange" /> Nouvelles boutiques (14 derniers jours)
          </h2>
          <TrendChart data={newStoresByDay} />
        </Card>
      </div>

      <Card className="flex items-center gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent text-orange">
          <ShieldCheck className="h-5 w-5" />
        </span>
        <p className="text-sm text-muted-foreground">
          Consultez « Boutiques » pour valider les nouvelles demandes d'ouverture.
        </p>
      </Card>
    </div>
  );
}

function Stat({ label, value, icon: Icon }: { label: string; value: number; icon: ComponentType<{ className?: string }> }) {
  return (
    <Card className="flex items-center gap-3">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent text-orange">
        <Icon className="h-5 w-5" />
      </span>
      <div>
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <p className="font-display text-2xl font-bold text-ink">{value}</p>
      </div>
    </Card>
  );
}
