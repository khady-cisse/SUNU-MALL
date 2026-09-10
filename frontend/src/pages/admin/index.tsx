import { type ComponentType, useCallback, useMemo } from "react";
import {
  AlertTriangle, ArrowRight, FileText, MessageSquare, RefreshCw,
  ShieldCheck, Store as StoreIcon, Users, Wrench, Search as SearchIcon,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAsync } from "@/hooks/useAsync";
import * as usersApi from "@/api/users";
import type { DailyCount } from "@/api/users";
import { apiGet } from "@/lib/api";
import { Card, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { TrendChart } from "@/components/ui/TrendChart";
import type { Paginated } from "@/types";

function toTrendPoints(daily: DailyCount[]) {
  return daily.map((d) => ({
    label: new Date(d.date).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" }),
    value: d.count,
  }));
}

interface ComplaintRow {
  id: string;
  status: string;
  priority: string;
}

const QUICK_ACTIONS = [
  { label: "Valider les boutiques", to: "/admin-shops", icon: StoreIcon, description: "Demandes d'ouverture" },
  { label: "Plaintes & litiges", to: "/admin-complaints", icon: MessageSquare, description: "Traitement du support" },
  { label: "Vérifications KYC", to: "/admin-kyc-sellers", icon: ShieldCheck, description: "Dossiers vendeurs & livreurs" },
  { label: "Remboursements", to: "/admin-refunds", icon: RefreshCw, description: "Demandes à traiter" },
  { label: "Incidents techniques", to: "/admin-incidents", icon: Wrench, description: "Résolution & statut" },
  { label: "Rapports & exports", to: "/admin-reports", icon: FileText, description: "PDF et CSV" },
  { label: "Recherche avancée", to: "/admin-search", icon: SearchIcon, description: "Toutes entités" },
];

export default function AdminDashboardPage() {
  const navigate = useNavigate();
  const { data: stats, loading: loadingStats, error: statsError, refetch: refetchStats } = useAsync(() => usersApi.getDashboardStats(), []);

  const openComplaintsFetcher = useCallback(
    () => apiGet<Paginated<ComplaintRow>>("/complaints/complaints/?status=open&priority=critical&page_size=1"),
    [],
  );
  const { data: criticalComplaints } = useAsync(openComplaintsFetcher, []);

  const newUsersByDay = useMemo(() => toTrendPoints(stats?.trend.new_users ?? []), [stats]);
  const newStoresByDay = useMemo(() => toTrendPoints(stats?.trend.new_stores ?? []), [stats]);

  if (loadingStats) return <Spinner label="Chargement des statistiques…" />;
  if (statsError) return <ErrorState message="Impossible de charger les statistiques." onRetry={refetchStats} />;
  if (!stats) return null;

  const alerts = [
    {
      priority: "high" as const,
      icon: StoreIcon,
      label: `${stats.stores.pending_review} boutique(s) en attente de validation`,
      to: "/admin-shops",
      tone: stats.stores.pending_review > 0 ? "orange" : undefined,
    },
    {
      priority: "medium" as const,
      icon: Users,
      label: `${stats.users.unverified} utilisateur(s) non vérifié(s)`,
      to: "/admin-users",
      tone: stats.users.unverified > 0 ? "orange" : undefined,
    },
    {
      priority: "critical" as const,
      icon: AlertTriangle,
      label: `${criticalComplaints?.count ?? 0} plainte(s) critique(s) ouverte(s)`,
      to: "/admin-complaints?status=open&priority=critical",
      tone: (criticalComplaints?.count ?? 0) > 0 ? "red" : undefined,
    },
  ].filter((a) => a.tone);

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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card>
          <CardTitle>Centre d'alertes</CardTitle>
          {alerts.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucune alerte nécessitant une action.</p>
          ) : (
            <ul className="space-y-3">
              {alerts.map((alert) => (
                <li key={alert.label}>
                  <button
                    onClick={() => navigate(alert.to)}
                    className="flex w-full items-center gap-3 rounded-xl border border-border p-3 text-left transition-colors hover:bg-muted/50"
                  >
                    <span
                      className={
                        alert.tone === "red"
                          ? "grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-red-50 text-red-600"
                          : "grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-orange-50 text-orange-600"
                      }
                    >
                      <alert.icon className="h-4 w-4" />
                    </span>
                    <span className="flex-1 text-sm font-medium text-ink">{alert.label}</span>
                    <Badge
                      variant={alert.tone === "red" ? "danger" : "warning"}
                      size="sm"
                    >
                      {alert.priority}
                    </Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardTitle>Actions rapides</CardTitle>
          <div className="grid gap-2 sm:grid-cols-2">
            {QUICK_ACTIONS.map((action) => (
              <button
                key={action.to}
                onClick={() => navigate(action.to)}
                className="group flex items-center gap-3 rounded-xl border border-border p-3 text-left transition-colors hover:border-orange-300 hover:bg-orange-50/50"
              >
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent text-orange">
                  <action.icon className="h-4 w-4" />
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-ink">{action.label}</span>
                  <span className="block truncate text-xs text-muted-foreground">{action.description}</span>
                </span>
              </button>
            ))}
          </div>
        </Card>
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
        <p className="flex-1 text-sm text-muted-foreground">
          Consultez « Boutiques » pour valider les nouvelles demandes d'ouverture.
        </p>
        <button
          onClick={() => navigate("/admin-shops")}
          className="inline-flex items-center gap-1 text-sm font-medium text-orange-600 hover:text-orange-700"
        >
          Ouvrir <ArrowRight className="h-4 w-4" />
        </button>
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