import { useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useAsync } from "@/hooks/useAsync";
import { apiGet } from "@/lib/api";
import { Card, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { StatCard } from "@/components/ui/StatCard";
import { formatDate, formatPrice } from "@/lib/utils";
import type { Paginated, Store, Product } from "@/types";

const TABS = ["Profil", "Produits", "Activité"] as const;

export default function AdminSellerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Profil");

  const storeFetcher = useCallback(() => apiGet<Store>(`/catalog/stores/${id}/`), [id]);
  const productsFetcher = useCallback(() => apiGet<Paginated<Product>>(`/catalog/products/?store=${id}`), [id]);
  const { data: store, loading, error, refetch } = useAsync(storeFetcher, [id]);
  const { data: products } = useAsync(productsFetcher, [id]);

  if (loading) return <Spinner label="Chargement du vendeur..." />;
  if (error) return <ErrorState message={error.message} onRetry={refetch} />;
  if (!store) return <ErrorState message="Vendeur introuvable" />;

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { label: "Dashboard", to: "/admin" },
          { label: "Vendeurs", to: "/admin-sellers" },
          { label: store.name },
        ]}
      />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          {store.logo_url ? (
            <img src={store.logo_url} alt="" className="h-14 w-14 rounded-lg object-cover" />
          ) : (
            <div className="grid h-14 w-14 place-items-center rounded-lg bg-muted text-lg font-bold text-muted-foreground">
              {store.name[0]}
            </div>
          )}
          <div>
            <h1 className="text-xl font-bold text-ink">{store.name}</h1>
            <p className="text-sm text-muted-foreground">{store.owner_email}</p>
            <div className="mt-1 flex gap-2">
              <StatusBadge status={store.status} />
              {store.is_verified_seller && <Badge variant="success" size="sm">Vérifié</Badge>}
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Statut" value={store.status} tone={store.status === "active" ? "green" : store.status === "suspended" ? "red" : "orange"} />
        <StatCard label="Note" value={store.rating ? `${store.rating}/5` : "—"} tone="orange" subtitle={`${store.review_count} avis`} />
        <StatCard label="Produits" value={products?.count ?? 0} tone="blue" />
        <StatCard label="Catégories" value={store.category_names?.join(", ") || "—"} tone="gray" />
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
            <CardTitle>Informations boutique</CardTitle>
            <div className="mt-3 space-y-3 text-sm">
              <div><p className="text-muted-foreground">Nom</p><p className="font-medium">{store.name}</p></div>
              <div><p className="text-muted-foreground">Téléphone</p><p>{store.phone || "—"}</p></div>
              <div><p className="text-muted-foreground">Adresse</p><p>{store.address}, {store.city}</p></div>
              <div><p className="text-muted-foreground">Description</p><p className="text-muted-foreground">{store.description || "—"}</p></div>
              <div><p className="text-muted-foreground">Créée le</p><p>{formatDate(store.created_at)}</p></div>
            </div>
          </Card>
          <Card>
            <CardTitle>Propriétaire</CardTitle>
            <div className="mt-3 space-y-3 text-sm">
              <div><p className="text-muted-foreground">Email</p><p>{store.owner_email}</p></div>
              <div><p className="text-muted-foreground">Vérifié KYC</p><StatusBadge status={store.is_verified_seller ? "VERIFIED" : "PENDING"} /></div>
            </div>
          </Card>
        </div>
      )}

      {tab === "Produits" && (
        <Card>
          <CardTitle>Produits ({products?.count ?? 0})</CardTitle>
          {(!products?.results || products.results.length === 0) ? (
            <p className="mt-4 text-sm text-muted-foreground">Aucun produit.</p>
          ) : (
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {products!.results.map((p) => (
                <div key={p.id} className="flex items-center gap-3 rounded-lg border border-border p-3">
                  {p.images?.[0]?.url ? (
                    <img src={p.images[0].url} alt="" className="h-12 w-12 rounded object-cover" />
                  ) : (
                    <div className="grid h-12 w-12 place-items-center rounded bg-muted text-xs text-muted-foreground">IMG</div>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">{p.name}</p>
                    <p className="text-xs text-muted-foreground">{formatPrice(p.base_price)}</p>
                  </div>
                  <StatusBadge status={p.status} />
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {tab === "Activité" && (
        <Card>
          <CardTitle>Activité récente</CardTitle>
          <p className="mt-3 text-sm text-muted-foreground">Historique des actions du vendeur.</p>
        </Card>
      )}
    </div>
  );
}
