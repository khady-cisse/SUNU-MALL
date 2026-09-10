import { useState, useCallback } from "react";
import { Flag } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { listSettings, updateSetting } from "@/api/ops";
import { Card, CardTitle } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { cn } from "@/lib/utils";

export default function AdminFeatureFlagsPage() {
  const fetcher = useCallback(() => listSettings(), []);
  const { data, loading, error, refetch } = useAsync(fetcher, []);
  const [toggling, setToggling] = useState<string | null>(null);

  const handleToggle = async (key: string, currentValue: string) => {
    setToggling(key);
    try {
      await updateSetting(key, currentValue === "true" ? "false" : "true");
      refetch();
    } catch { /* handled */ }
    setToggling(null);
  };

  if (loading) return <Spinner label="Chargement des feature flags..." />;
  if (error) return <ErrorState message={error.message} onRetry={refetch} />;

  const settings = data?.results ?? [];
  const flags = settings.filter((s) => s.setting_type === "bool" || s.key.toLowerCase().includes("flag") || s.key.toLowerCase().includes("maintenance") || s.key.toLowerCase().includes("enabled") || s.key.toLowerCase().includes("active"));

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Feature Flags" }]} />
      <Card>
        <CardTitle>Feature Flags</CardTitle>
        <p className="mt-1 text-sm text-muted-foreground">Activez ou désactivez des fonctionnalités sans redéploiement.</p>
        <div className="mt-4 divide-y divide-border">
          {flags.length === 0 && <p className="py-8 text-center text-sm text-muted-foreground">Aucun feature flag trouvé.</p>}
          {flags.map((flag) => {
            const isEnabled = flag.value === "true";
            return (
              <div key={flag.id} className="flex items-center justify-between py-3">
                <div className="flex items-center gap-3">
                  <Flag className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="font-medium text-ink">{flag.key}</p>
                    {flag.description && <p className="text-xs text-muted-foreground">{flag.description}</p>}
                  </div>
                </div>
                <button
                  onClick={() => handleToggle(flag.key, flag.value)}
                  disabled={toggling === flag.key}
                  className={cn(
                    "relative h-6 w-11 rounded-full transition-colors",
                    isEnabled ? "bg-green-500" : "bg-gray-300",
                    toggling === flag.key && "opacity-50",
                  )}
                >
                  <span className={cn("absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform", isEnabled && "translate-x-5")} />
                </button>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
