import { useState, useCallback } from "react";
import { BarChart3 } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { apiGet } from "@/lib/api";
import { Card, CardTitle } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { TrendChart } from "@/components/ui/TrendChart";

interface DashboardStats {
  users: { total: number; active: number; unverified: number };
  stores: { total: number; active: number; pending_review: number; suspended: number };
  orders: { total: number; pending: number; delivered: number; cancelled: number };
  payments: { total: number; success: number; failed: number };
  complaints: { total: number; open: number; resolved: number };
  subscriptions: { total: number; active: number; expiring: number };
  trend: { new_users: { date: string; count: number }[]; new_orders: { date: string; count: number }[] };
}

export default function AdminAnalyticsPage() {
  const [period, setPeriod] = useState("30");

  const fetcher = useCallback(
    () => apiGet<DashboardStats>(`/users/admin/dashboard/stats/?days=${period}`),
    [period],
  );
  const { data, loading, error, refetch } = useAsync(fetcher, [period]);

  if (loading) return <Spinner label="Chargement des analytics..." />;
  if (error) return <ErrorState message={error.message} onRetry={refetch} />;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Analytics" }]} />

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-ink">Analytics</h1>
        <select
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          className="rounded-lg border border-border bg-white px-3 py-2 text-sm"
        >
          <option value="1">Aujourd'hui</option>
          <option value="7">7 jours</option>
          <option value="30">30 jours</option>
          <option value="90">3 mois</option>
          <option value="180">6 mois</option>
          <option value="365">1 an</option>
        </select>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Utilisateurs" value={data.users.total} icon={<BarChart3 className="h-5 w-5" />} tone="orange" subtitle={`${data.users.active} actifs`} />
        <StatCard label="Boutiques" value={data.stores.total} tone="green" subtitle={`${data.stores.active} actives`} />
        <StatCard label="Commandes" value={data.orders.total} tone="blue" subtitle={`${data.orders.delivered} livrées`} />
        <StatCard label="Paiements" value={data.payments.total} tone="purple" subtitle={`${data.payments.failed} échoués`} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard label="Plaintes" value={data.complaints.total} tone="red" subtitle={`${data.complaints.open} ouvertes`} />
        <StatCard label="Abonnements" value={data.subscriptions.total} tone="green" subtitle={`${data.subscriptions.active} actifs`} />
        <StatCard label="Revenus" value={`${data.payments.success}`} tone="orange" subtitle="Paiements réussis" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle>Nouveaux utilisateurs</CardTitle>
          <div className="mt-4">
            <TrendChart
              data={(data.trend?.new_users ?? []).map((d) => ({ label: d.date, value: d.count }))}
            />
          </div>
        </Card>
        <Card>
          <CardTitle>Nouvelles commandes</CardTitle>
          <div className="mt-4">
            <TrendChart
              data={(data.trend?.new_orders ?? []).map((d) => ({ label: d.date, value: d.count }))}
            />
          </div>
        </Card>
      </div>
    </div>
  );
}
