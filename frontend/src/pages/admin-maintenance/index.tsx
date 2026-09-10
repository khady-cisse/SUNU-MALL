import { useState, useCallback } from "react";
import { Wrench } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import { listSettings, updateSetting } from "@/api/ops";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { cn } from "@/lib/utils";

export default function AdminMaintenancePage() {
  const fetcher = useCallback(() => listSettings(), []);
  const { data, loading, error, refetch } = useAsync(fetcher, []);
  const [showConfirm, setShowConfirm] = useState(false);
  const [saving, setSaving] = useState(false);

  const maintenanceSetting = data?.results?.find((s) => s.key === "maintenance_mode");
  const isMaintenance = maintenanceSetting?.value === "true";

  const handleToggle = async () => {
    setSaving(true);
    try {
      await updateSetting("maintenance_mode", isMaintenance ? "false" : "true");
      refetch();
    } catch { /* handled */ }
    setSaving(false);
    setShowConfirm(false);
  };

  if (loading) return <Spinner label="Chargement..." />;
  if (error) return <ErrorState message={error.message} onRetry={refetch} />;

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Maintenance" }]} />
      <Card>
        <CardTitle>Mode maintenance</CardTitle>
        <p className="mt-2 text-sm text-muted-foreground">
          Lorsque le mode maintenance est activé, seuls les administrateurs peuvent accéder à la plateforme.
        </p>
        <div className="mt-6 flex items-center gap-4">
          <div className={cn(
            "flex items-center gap-3 rounded-xl border p-4",
            isMaintenance ? "border-red-200 bg-red-50" : "border-green-200 bg-green-50",
          )}>
            <Wrench className={cn("h-5 w-5", isMaintenance ? "text-red-600" : "text-green-600")} />
            <div>
              <p className="font-medium text-ink">{isMaintenance ? "Mode maintenance ACTIVÉ" : "Plateforme opérationnelle"}</p>
              <p className="text-xs text-muted-foreground">{isMaintenance ? "Les utilisateurs voient la page de maintenance." : "Tous les accès sont ouverts."}</p>
            </div>
          </div>
          <Button
            variant={isMaintenance ? "primary" : "danger"}
            onClick={() => setShowConfirm(true)}
            loading={saving}
          >
            {isMaintenance ? "Désactiver le mode maintenance" : "Activer le mode maintenance"}
          </Button>
        </div>
      </Card>

      <ConfirmDialog
        open={showConfirm}
        onClose={() => setShowConfirm(false)}
        onConfirm={handleToggle}
        title={isMaintenance ? "Désactiver le mode maintenance ?" : "Activer le mode maintenance ?"}
        message={isMaintenance
          ? "La plateforme sera de nouveau accessible aux utilisateurs."
          : "Seuls les administrateurs pourront accéder à la plateforme. Les utilisateurs verront une page de maintenance."
        }
        confirmLabel={isMaintenance ? "Désactiver" : "Activer"}
        loading={saving}
      />
    </div>
  );
}
