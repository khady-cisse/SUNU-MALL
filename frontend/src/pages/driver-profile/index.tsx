import { useEffect, useState } from "react";
import { CheckCircle2, Truck, TriangleAlert, User } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { DriverAvailability } from "@/types";

const AVAILABILITY_OPTIONS: { value: DriverAvailability; label: string }[] = [
  { value: "available", label: "Disponible" },
  { value: "busy", label: "Occupé" },
  { value: "offline", label: "Hors ligne" },
];

export default function DriverProfilePage() {
  const { data: driver, loading, refetch } = useAsync(() => ordersApi.getMyDriverProfile(), []);
  const [vehicleType, setVehicleType] = useState("");
  const [availability, setAvailability] = useState<DriverAvailability>("offline");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (!driver) return;
    setVehicleType(driver.vehicle_type);
    setAvailability(driver.availability_status);
  }, [driver]);

  async function handleSave() {
    setSaving(true);
    setFeedback(null);
    try {
      if (availability === "available") {
        const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
          if (!("geolocation" in navigator)) {
            reject(new Error("GPS non disponible"));
            return;
          }
          navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 10000 });
        });
        await ordersApi.updateMyDriverPosition(pos.coords.latitude, pos.coords.longitude);
      }
      await ordersApi.updateMyDriverProfile({ vehicle_type: vehicleType, availability_status: availability });
      setFeedback({ type: "success", text: "Profil mis à jour." });
      refetch();
    } catch (err) {
      setFeedback({
        type: "error",
        text:
          availability === "available" && err instanceof Error && err.message === "GPS non disponible"
            ? "Activez la géolocalisation : votre position GPS est requise pour être disponible à proximité des boutiques."
            : err instanceof ApiError
              ? "Impossible d'enregistrer."
              : "Impossible de contacter le serveur.",
      });
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Spinner label="Chargement du profil…" />;
  if (!driver) return null;

  return (
    <div className="max-w-lg">
      <h1 className="mb-6 flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
        <Truck className="h-6 w-6 text-orange" /> Mon profil
      </h1>

      <Card className="flex flex-col gap-5">
        <div className="flex items-center gap-3 border-b border-border pb-4">
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-gradient-orange text-base font-bold text-white shadow-orange">
            {driver.full_name.slice(0, 2).toUpperCase() || <User className="h-5 w-5" />}
          </span>
          <div>
            <p className="font-semibold text-ink">{driver.full_name}</p>
            <p className="text-sm text-muted-foreground">{driver.phone || "Téléphone non renseigné"}</p>
          </div>
        </div>

        <Input
          label="Type de véhicule"
          placeholder="Moto, vélo, voiture…"
          value={vehicleType}
          onChange={(e) => setVehicleType(e.target.value)}
        />

        <Select
          label="Disponibilité"
          value={availability}
          onChange={(e) => setAvailability(e.target.value as DriverAvailability)}
        >
          {AVAILABILITY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>

        {feedback && (
          <div
            className={cn(
              "flex items-center gap-2 rounded-lg border px-3.5 py-2.5 text-sm font-medium",
              feedback.type === "success" ? "border-green-200 bg-green-50 text-green-700" : "border-danger/30 bg-red-50 text-danger",
            )}
          >
            {feedback.type === "success" ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <TriangleAlert className="h-4 w-4 shrink-0" />}
            {feedback.text}
          </div>
        )}

        <Button onClick={handleSave} loading={saving} className="self-start">
          Enregistrer
        </Button>
      </Card>
    </div>
  );
}
