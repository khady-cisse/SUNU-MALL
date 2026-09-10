import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Search, User, Store, ShoppingCart, CreditCard, Truck, AlertTriangle, FileText, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiGet } from "@/lib/api";

interface SearchResult {
  type: string;
  label: string;
  subtitle?: string;
  to: string;
}

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  users: <User className="h-4 w-4" />,
  sellers: <Store className="h-4 w-4" />,
  stores: <Store className="h-4 w-4" />,
  products: <ShoppingCart className="h-4 w-4" />,
  orders: <FileText className="h-4 w-4" />,
  payments: <CreditCard className="h-4 w-4" />,
  drivers: <Truck className="h-4 w-4" />,
  complaints: <AlertTriangle className="h-4 w-4" />,
};

const CATEGORY_LABELS: Record<string, string> = {
  users: "UTILISATEURS",
  sellers: "VENDEURS",
  stores: "BOUTIQUES",
  products: "PRODUITS",
  orders: "COMMANDES",
  payments: "PAIEMENTS",
  drivers: "LIVREURS",
  complaints: "PLAINTES",
};

export function GlobalSearchModal() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Record<string, SearchResult[]>>({});
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const abortRef = useRef<AbortController | null>(null);

  const allResults = Object.values(results).flat();

  const executeSearch = useCallback(async (q: string) => {
    if (q.trim().length < 2) {
      setResults({});
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    try {
      const data = await apiGet<Record<string, SearchResult[]>>(`/search/?q=${encodeURIComponent(q)}`);
      setResults(data);
      setActiveIndex(0);
    } catch {
      setResults({});
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => executeSearch(query), 250);
    return () => clearTimeout(t);
  }, [query, executeSearch]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setQuery("");
      setResults({});
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
      if (e.key === "ArrowDown") { e.preventDefault(); setActiveIndex((i) => Math.min(i + 1, allResults.length - 1)); }
      if (e.key === "ArrowUp") { e.preventDefault(); setActiveIndex((i) => Math.max(i - 1, 0)); }
      if (e.key === "Enter" && allResults[activeIndex]) {
        navigate(allResults[activeIndex].to);
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, allResults, activeIndex, navigate]);

  const handleSelect = (to: string) => {
    navigate(to);
    setOpen(false);
  };

  if (!open) return null;

  let flatIdx = 0;

  return (
    <div className="fixed inset-0 z-[60] grid place-items-start justify-center bg-black/40 pt-[15vh]" onClick={() => setOpen(false)}>
      <div
        className="w-full max-w-lg rounded-xl bg-white shadow-elevated overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-border px-4 py-3">
          <Search className="h-5 w-5 text-muted-foreground" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Rechercher un utilisateur, vendeur, commande, produit, plainte..."
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <kbd className="hidden rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground sm:inline">ESC</kbd>
          <button onClick={() => setOpen(false)} className="rounded p-0.5 text-muted-foreground hover:text-ink">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto">
          {loading && (
            <div className="py-8 text-center text-sm text-muted-foreground">Recherche en cours...</div>
          )}

          {!loading && query.length >= 2 && Object.keys(results).length === 0 && (
            <div className="py-8 text-center text-sm text-muted-foreground">Aucun résultat trouvé.</div>
          )}

          {!loading && Object.entries(results).map(([category, items]) => {
            const catLabel = CATEGORY_LABELS[category] ?? category.toUpperCase();
            const catIcon = CATEGORY_ICONS[category];
            return (
              <div key={category}>
                <div className="flex items-center gap-2 bg-muted/40 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {catIcon}
                  {catLabel}
                  <span className="ml-auto text-muted-foreground/60">{items.length} résultat{items.length > 1 ? "s" : ""}</span>
                </div>
                {items.map((item) => {
                  const idx = flatIdx++;
                  return (
                    <button
                      key={item.to}
                      onClick={() => handleSelect(item.to)}
                      className={cn(
                        "flex w-full items-start gap-3 px-4 py-2.5 text-left transition-colors hover:bg-muted/50",
                        idx === activeIndex && "bg-orange-50",
                      )}
                    >
                      <div className="mt-0.5 text-muted-foreground">{catIcon}</div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink">{item.label}</p>
                        {item.subtitle && <p className="truncate text-xs text-muted-foreground">{item.subtitle}</p>}
                      </div>
                    </button>
                  );
                })}
              </div>
            );
          })}

          {query.length < 2 && (
            <div className="py-8 text-center text-xs text-muted-foreground">
              Tapez au moins 2 caractères pour lancer la recherche.
              <br />
              <kbd className="mt-2 inline rounded border border-border bg-muted px-1.5 py-0.5">Ctrl + K</kbd> pour ouvrir/fermer
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
