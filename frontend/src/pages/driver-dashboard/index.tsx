import { Link } from "react-router-dom";
import { ChevronRight, PackageSearch, Truck } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { KycStatusCard } from "@/components/kyc/KycStatusCard";
import { formatDate } from "@/lib/utils";
import { DELIVERY_STATUS_LABEL, DELIVERY_STATUS_VARIANT } from "@/lib/delivery";
import type { DriverAvailability } from "@/types";

const TERMINAL_STATUSES = new Set(["delivered", "delivery_failed", "customer_unavailable", "returned", "cancelled"]);

const AVAILABILITY_LABEL: Record<DriverAvailability, string> = {
  available: "Disponible",
  busy: "Occupé",
  offline: "Hors ligne",
};

export default function DriverDashboardPage() {
  const { data: driver, refetch: refetchDriver } = useAsync(() => ordersApi.getMyDriverProfile(), []);
  const { data: deliveries, loading } = useAsync(() => ordersApi.listDeliveries(), []);

  async function toggleAvailability() {
    if (!driver) return;
    const next: DriverAvailability = driver.availability_status === "available" ? "offline" : "available";
    await ordersApi.updateMyDriverProfile({ availability_status: next });
    refetchDriver();
  }

  const active = deliveries?.filter((d) => !TERMINAL_STATUSES.has(d.status)) ?? [];
  const history = deliveries?.filter((d) => TERMINAL_STATUSES.has(d.status)) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <KycStatusCard kind="driver" />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
          <Truck className="h-6 w-6 text-orange" /> Mes courses
        </h1>
        {driver && (
          <button
            onClick={toggleAvailability}
            className="focus-ring flex items-center gap-2 rounded-lg border border-border bg-white px-4 py-2 text-sm font-semibold text-ink transition-colors hover:border-orange/50"
          >
            <span
              className={`h-2.5 w-2.5 rounded-full ${driver.availability_status === "available" ? "bg-success" : "bg-muted-foreground"}`}
            />
            {AVAILABILITY_LABEL[driver.availability_status]}
          </button>
        )}
      </div>

      {loading ? (
        <Spinner label="Chargement de vos courses…" />
      ) : (
        <>
          <div>
            <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-muted-foreground">En cours</h2>
            {active.length === 0 ? (
              <EmptyState icon={PackageSearch} title="Aucune course en cours" description="Les nouvelles courses affectées apparaîtront ici." />
            ) : (
              <div className="flex flex-col gap-3">
                {active.map((delivery) => (
                  <Link key={delivery.id} to={`/driver-delivery?delivery=${delivery.id}`}>
                    <Card variant="interactive" className="flex items-center justify-between">
                      <div>
                        <p className="text-xs text-muted-foreground">{formatDate(delivery.created_at)}</p>
                        <p className="font-semibold text-ink">Commande n°{delivery.order.slice(0, 8)}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge variant={DELIVERY_STATUS_VARIANT[delivery.status]}>{DELIVERY_STATUS_LABEL[delivery.status]}</Badge>
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      </div>
                    </Card>
                  </Link>
                ))}
              </div>
            )}
          </div>

          {history.length > 0 && (
            <div>
              <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-muted-foreground">Historique</h2>
              <div className="flex flex-col gap-3">
                {history.map((delivery) => (
                  <Link key={delivery.id} to={`/driver-delivery?delivery=${delivery.id}`}>
                    <Card variant="interactive" className="flex items-center justify-between opacity-70">
                      <div>
                        <p className="text-xs text-muted-foreground">{formatDate(delivery.created_at)}</p>
                        <p className="font-medium text-ink">Commande n°{delivery.order.slice(0, 8)}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge variant={DELIVERY_STATUS_VARIANT[delivery.status]}>{DELIVERY_STATUS_LABEL[delivery.status]}</Badge>
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      </div>
                    </Card>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
