import { useCallback } from "react";
import { Tag } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { apiGet } from "@/lib/api";
import { Card, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import type { Paginated, Category } from "@/types";

export default function AdminCategoriesPage() {
  const fetcher = useCallback(() => apiGet<Paginated<Category>>("/catalog/categories/"), []);
  const { data, loading, error, refetch } = useAsync(fetcher, []);

  if (loading) return <Spinner label="Chargement des catégories..." />;
  if (error) return <ErrorState message={error.message} onRetry={refetch} />;

  const categories = data?.results ?? [];
  const parents = categories.filter((c) => !c.parent);
  const childrenMap = new Map<string, Category[]>();
  categories.forEach((c) => {
    if (c.parent) {
      const list = childrenMap.get(c.parent) ?? [];
      list.push(c);
      childrenMap.set(c.parent, list);
    }
  });

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Catégories" }]} />
      <Card>
        <CardTitle>Catégories</CardTitle>
        {parents.length === 0 ? (
          <EmptyState icon={Tag} title="Aucune catégorie" description="Aucune catégorie n'a été créée." />
        ) : (
          <div className="mt-4 space-y-4">
            {parents.map((cat) => {
              const children = childrenMap.get(cat.id) ?? [];
              return (
                <div key={cat.id} className="rounded-lg border border-border p-4">
                  <div className="flex items-center gap-3">
                    {cat.image_url ? (
                      <img src={cat.image_url} alt="" className="h-10 w-10 rounded object-cover" />
                    ) : (
                      <div className="grid h-10 w-10 place-items-center rounded bg-muted">
                        <Tag className="h-5 w-5 text-muted-foreground" />
                      </div>
                    )}
                    <div>
                      <p className="font-medium text-ink">{cat.name}</p>
                      <p className="text-xs text-muted-foreground">{children.length} sous-catégorie{children.length > 1 ? "s" : ""}</p>
                    </div>
                  </div>
                  {children.length > 0 && (
                    <div className="mt-3 ml-13 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
                      {children.map((child) => (
                        <div key={child.id} className="rounded bg-muted/50 px-3 py-2 text-sm text-ink">
                          {child.name}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
