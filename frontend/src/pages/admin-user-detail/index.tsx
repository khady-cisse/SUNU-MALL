import { useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useAsync } from "@/hooks/useAsync";
import { apiGet } from "@/lib/api";
import { setUserActive } from "@/api/users";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { formatDate } from "@/lib/utils";
import type { Paginated } from "@/types";

interface UserDetail {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  is_active: boolean;
  is_verified: boolean;
  roles: string[];
  created_at: string;
  last_login: string | null;
}

interface UserOrder {
  id: string;
  store_name: string;
  total_amount: string;
  status: string;
  created_at: string;
}

const TABS = ["Profil", "Commandes", "Activité"] as const;

export default function AdminUserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Profil");
  const [showSuspend, setShowSuspend] = useState(false);
  const [saving, setSaving] = useState(false);

  const userFetcher = useCallback(() => apiGet<UserDetail>(`/users/${id}/`), [id]);
  const ordersFetcher = useCallback(() => apiGet<Paginated<UserOrder>>(`/orders/?customer=${id}`), [id]);
  const { data: user, loading, error, refetch } = useAsync(userFetcher, [id]);
  const { data: orders } = useAsync(ordersFetcher, [id]);

  const handleToggleActive = async () => {
    if (!user) return;
    setSaving(true);
    try {
      await setUserActive(user.id, !user.is_active);
      refetch();
    } catch { /* handled */ }
    setSaving(false);
    setShowSuspend(false);
  };

  if (loading) return <Spinner label="Chargement du profil..." />;
  if (error) return <ErrorState message={error.message} onRetry={refetch} />;
  if (!user) return <ErrorState message="Utilisateur introuvable" />;

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { label: "Dashboard", to: "/admin" },
          { label: "Utilisateurs", to: "/admin-users" },
          { label: `${user.first_name} ${user.last_name}` },
        ]}
      />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="grid h-14 w-14 place-items-center rounded-full bg-gradient-orange text-lg font-bold text-white">
            {user.first_name?.[0]}{user.last_name?.[0]}
          </div>
          <div>
            <h1 className="text-xl font-bold text-ink">{user.first_name} {user.last_name}</h1>
            <p className="text-sm text-muted-foreground">{user.email}</p>
            <div className="mt-1 flex gap-1.5">
              {user.roles.map((r) => (
                <Badge key={r} variant={r === "admin" ? "danger" : r === "merchant" ? "warning" : "default"} size="sm">{r}</Badge>
              ))}
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant={user.is_active ? "danger" : "primary"}
            size="sm"
            loading={saving}
            onClick={() => setShowSuspend(true)}
          >
            {user.is_active ? "Suspendre" : "Réactiver"}
          </Button>
        </div>
      </div>

      <div className="flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors ${tab === t ? "border-b-2 border-orange-500 text-orange-600" : "text-muted-foreground hover:text-ink"}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Profil" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardTitle>Informations personnelles</CardTitle>
            <div className="mt-3 space-y-3 text-sm">
              <div><p className="text-muted-foreground">Nom complet</p><p className="font-medium">{user.first_name} {user.last_name}</p></div>
              <div><p className="text-muted-foreground">Email</p><p>{user.email}</p></div>
              <div><p className="text-muted-foreground">Téléphone</p><p>{user.phone || "—"}</p></div>
              <div><p className="text-muted-foreground">Inscrit le</p><p>{formatDate(user.created_at)}</p></div>
              <div><p className="text-muted-foreground">Dernière connexion</p><p>{user.last_login ? formatDate(user.last_login) : "Jamais"}</p></div>
            </div>
          </Card>
          <Card>
            <CardTitle>Statut</CardTitle>
            <div className="mt-3 space-y-3 text-sm">
              <div className="flex items-center gap-2"><p className="text-muted-foreground">Compte</p><StatusBadge status={user.is_active ? "active" : "suspended"} /></div>
              <div className="flex items-center gap-2"><p className="text-muted-foreground">Email vérifié</p><StatusBadge status={user.is_verified ? "success" : "pending"} /></div>
            </div>
          </Card>
        </div>
      )}

      {tab === "Commandes" && (
        <Card>
          <CardTitle>Commandes ({orders?.count ?? 0})</CardTitle>
          {(!orders?.results || orders.results.length === 0) ? (
            <p className="mt-4 text-sm text-muted-foreground">Aucune commande.</p>
          ) : (
            <div className="mt-4 space-y-2">
              {orders!.results.map((o) => (
                <div key={o.id} className="flex items-center justify-between rounded-lg border border-border px-4 py-3">
                  <div>
                    <p className="text-sm font-medium">{o.store_name}</p>
                    <p className="text-xs text-muted-foreground">{formatDate(o.created_at)}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={o.status} />
                    <span className="text-sm font-medium">{o.total_amount} FCFA</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {tab === "Activité" && (
        <Card>
          <CardTitle>Activité récente</CardTitle>
          <p className="mt-3 text-sm text-muted-foreground">Historique des actions de l'utilisateur.</p>
        </Card>
      )}

      <ConfirmDialog
        open={showSuspend}
        onClose={() => setShowSuspend(false)}
        onConfirm={handleToggleActive}
        title={user.is_active ? "Suspendre cet utilisateur ?" : "Réactiver cet utilisateur ?"}
        message={user.is_active ? "L'utilisateur ne pourra plus se connecter." : "L'utilisateur pourra de nouveau se connecter."}
        confirmLabel={user.is_active ? "Suspendre" : "Réactiver"}
        loading={saving}
      />
    </div>
  );
}
