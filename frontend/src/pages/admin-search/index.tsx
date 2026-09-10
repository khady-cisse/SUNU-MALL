import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Search, ArrowRight, Save } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { advancedSearch, type SearchResultItem } from "@/api/search";
import { useSavedSearchesStore } from "@/store/savedSearchesStore";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { cn } from "@/lib/utils";

const ENTITIES = [
  { key: "users", label: "Utilisateurs" },
  { key: "stores", label: "Boutiques" },
  { key: "products", label: "Produits" },
  { key: "orders", label: "Commandes" },
  { key: "payments", label: "Paiements" },
  { key: "deliveries", label: "Livraisons" },
  { key: "complaints", label: "Plaintes" },
  { key: "drivers", label: "Livreurs" },
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  users: "Utilisateurs",
  stores: "Boutiques",
  products: "Produits",
  orders: "Commandes",
  payments: "Paiements",
  deliveries: "Livraisons",
  complaints: "Plaintes",
  drivers: "Livreurs",
};

export default function AdminSearchPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedEntities, setSelectedEntities] = useState<string[]>([...ENTITIES.map((e) => e.key)]);
  const [status, setStatus] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [saveName, setSaveName] = useState("");
  const { saved, addSearch } = useSavedSearchesStore();

  const filters = {
    q: searchTerm,
    entities: selectedEntities,
    status,
    date_from: dateFrom,
    date_to: dateTo,
  };

  const entitiesKey = selectedEntities.join(",");

  const fetcher = useCallback(
    () =>
      advancedSearch({
        q: searchTerm,
        entities: entitiesKey ? entitiesKey.split(",") : [],
        status,
        date_from: dateFrom,
        date_to: dateTo,
      }),
    [searchTerm, entitiesKey, status, dateFrom, dateTo],
  );

  const { data: results, loading, error, refetch } = useAsync(fetcher, [searchTerm, entitiesKey, status, dateFrom, dateTo]);

  const toggleEntity = (key: string) =>
    setSelectedEntities((prev) =>
      prev.includes(key) ? prev.filter((e) => e !== key) : [...prev, key],
    );

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim().length >= 1) setSearchTerm(query.trim());
  };

  const handleSave = () => {
    const name = saveName.trim() || `Recherche du ${new Date().toLocaleDateString("fr-FR")}`;
    addSearch(name, filters);
    setSaveName("");
  };

  const totalResults = results ? Object.values(results).flat().length : 0;

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Recherche avancée" }]} />

      <Card>
        <CardTitle>Recherche avancée</CardTitle>
        <form onSubmit={handleSearch} className="mt-4 flex flex-col gap-4">
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Rechercher un utilisateur, vendeur, commande, produit, plainte..."
                className="h-10 w-full rounded-lg border border-border bg-white pl-9 pr-4 text-sm outline-none focus:border-orange-400 focus:ring-2 focus:ring-orange-100"
              />
            </div>
            <Button type="submit" disabled={query.trim().length < 1}>
              Rechercher
            </Button>
          </div>

          <div className="flex flex-wrap gap-2">
            {ENTITIES.map((e) => (
              <button
                key={e.key}
                type="button"
                onClick={() => toggleEntity(e.key)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                  selectedEntities.includes(e.key)
                    ? "border-orange-500 bg-orange-50 text-orange-700"
                    : "border-border bg-white text-muted-foreground hover:bg-muted/50",
                )}
              >
                {e.label}
              </button>
            ))}
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <input
              type="text"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              placeholder="Statut (ex : active, pending, delivered...)"
              className="h-10 rounded-lg border border-border bg-white px-3 text-sm outline-none focus:border-orange-400"
            />
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="h-10 rounded-lg border border-border bg-white px-3 text-sm outline-none focus:border-orange-400"
            />
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="h-10 rounded-lg border border-border bg-white px-3 text-sm outline-none focus:border-orange-400"
            />
          </div>
        </form>

        <div className="mt-4 border-t border-border pt-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1">
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Enregistrer cette recherche
              </label>
              <input
                type="text"
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
                placeholder="Nom de la recherche (ex : vendeurs suspendus)"
                className="h-10 w-full rounded-lg border border-border bg-white px-3 text-sm outline-none focus:border-orange-400"
              />
            </div>
            <Button type="button" variant="secondary" size="sm" onClick={handleSave}>
              <Save className="h-3 w-3" /> Enregistrer
            </Button>
          </div>

          {saved.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {saved.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => {
                    setQuery(s.filters.q ?? "");
                    setSearchTerm(s.filters.q ?? "");
                    setSelectedEntities(s.filters.entities?.length ? s.filters.entities : ENTITIES.map((e) => e.key));
                    setStatus(s.filters.status ?? "");
                    setDateFrom(s.filters.date_from ?? "");
                    setDateTo(s.filters.date_to ?? "");
                  }}
                  className="rounded-full border border-border px-3 py-1 text-xs text-ink hover:bg-muted/50"
                  title={new Date(s.createdAt).toLocaleString("fr-FR")}
                >
                  {s.name}
                </button>
              ))}
            </div>
          )}
        </div>
      </Card>

      {loading && <Spinner label="Recherche en cours..." />}

      {error && <ErrorState message={error.message} onRetry={refetch} />}

      {results && !loading && totalResults === 0 && (
        <EmptyState title="Aucun résultat trouvé" description="Essayez avec d'autres termes ou filtres." />
      )}

      {results && !loading && totalResults > 0 && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">{totalResults} résultat{totalResults > 1 ? "s" : ""} trouvé{totalResults > 1 ? "s" : ""}</p>
          {Object.entries(results).map(([category, items]) => (
            <Card key={category}>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-ink">
                  {CATEGORY_LABELS[category] ?? category}
                </h3>
                <Badge size="sm">{items.length}</Badge>
              </div>
              <div className="divide-y divide-border">
                {items.map((item: SearchResultItem) => (
                  <button
                    key={`${category}-${item.to}`}
                    onClick={() => navigate(item.to)}
                    className="flex w-full items-center justify-between px-3 py-2.5 text-left transition-colors hover:bg-muted/50 rounded-lg"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-ink truncate">{item.label}</p>
                      {item.subtitle && <p className="text-xs text-muted-foreground truncate">{item.subtitle}</p>}
                    </div>
                    <span className="flex items-center gap-2">
                      {item.meta?.status && <Badge variant="default" size="sm">{item.meta.status}</Badge>}
                      <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                    </span>
                  </button>
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}