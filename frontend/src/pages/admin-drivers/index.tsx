import { useState } from "react";
import { Truck, TriangleAlert, Check, Copy } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ApiError } from "@/lib/api";

const STATUS_VARIANT: Record<string, "default" | "success" | "warning"> = {
  available: "success",
  busy: "warning",
  offline: "default",
};

const STATUS_LABEL: Record<string, string> = {
  available: "Disponible",
  busy: "En course",
  offline: "Hors ligne",
};

export default function AdminDriversPage() {
  const {
    data: drivers,
    loading,
    error,
    refetch,
  } = useAsync(() => ordersApi.listAvailableDrivers(), []);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [createdPassword, setCreatedPassword] = useState<{ driver: string; password: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [form, setForm] = useState({
    email: "",
    first_name: "",
    last_name: "",
    phone: "",
    vehicle_type: "moto",
  });

  function update<K extends keyof typeof form>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setCreatedPassword(null);
    setCreating(true);
    try {
      const result = await ordersApi.registerDriver({
        email: form.email.trim(),
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        phone: form.phone.trim(),
        vehicle_type: form.vehicle_type.trim(),
      });
      setCreatedPassword({ driver: result.full_name || result.email || "", password: result.temporary_password });
      setForm({ email: "", first_name: "", last_name: "", phone: "", vehicle_type: "moto" });
      refetch();
    } catch (err) {
      if (err instanceof ApiError) {
        const data = Array.isArray(err.data)
          ? (err.data as unknown[]).join(" ")
          : typeof err.data === "string" || (err.data && typeof err.data === "object" && "error" in (err.data as Record<string, unknown>))
            ? String((err.data as { error?: unknown }).error ?? err.data)
            : "Impossible de créer le livreur.";
        setFormError(data);
      } else {
        setFormError("Impossible de créer le livreur.");
      }
    } finally {
      setCreating(false);
    }
  }

  async function handleCopyPassword() {
    if (!createdPassword) return;
    try {
      await navigator.clipboard.writeText(createdPassword.password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  if (loading) return <Spinner label="Chargement des livreurs…" />;

  return (
    <div>
      <h1 className="mb-1 flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
        <Truck className="h-6 w-6 text-orange" /> Livreurs
      </h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Créez des comptes livreurs. Votre livreur devra changer son mot de passe à sa première connexion,
        puis partager sa position GPS pour être éligible aux commandes.
      </p>

      {error ? (
        <ErrorState fullPage onRetry={refetch} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="h-fit">
            <h2 className="mb-1 font-semibold text-ink">Créer un livreur</h2>
            <p className="mb-4 text-xs text-muted-foreground">
              Le mot de passe provisoire est affiché une seule fois après la création.
            </p>

            <form onSubmit={handleCreate} className="flex flex-col gap-4">
              <Input
                label="Prénom"
                value={form.first_name}
                onChange={(e) => update("first_name", e.target.value)}
                required
              />
              <Input
                label="Nom"
                value={form.last_name}
                onChange={(e) => update("last_name", e.target.value)}
                required
              />
              <Input
                label="Email"
                type="email"
                value={form.email}
                onChange={(e) => update("email", e.target.value)}
                required
              />
              <Input
                label="Téléphone"
                type="tel"
                value={form.phone}
                onChange={(e) => update("phone", e.target.value)}
                placeholder="+221..."
              />
              <label className="flex flex-col gap-1.5">
                <span className="text-sm font-medium text-ink">Type de véhicule</span>
                <select
                  value={form.vehicle_type}
                  onChange={(e) => update("vehicle_type", e.target.value)}
                  className="focus-ring w-full rounded-lg border border-border bg-white px-3.5 py-2.5 text-sm text-ink"
                >
                  <option value="moto">Moto</option>
                  <option value="velo">Vélo</option>
                  <option value="voiture">Voiture</option>
                  <option value="pieton">À pied</option>
                </select>
              </label>

              {formError && (
                <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
                  <TriangleAlert className="h-4 w-4 shrink-0" />
                  {formError}
                </div>
              )}

              <Button type="submit" loading={creating} className="mt-1 self-start">
                Créer le compte
              </Button>
            </form>

            {createdPassword && (
              <div className="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-50 p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-emerald-700">
                  <Check className="h-4 w-4" /> Compte créé pour {createdPassword.driver}
                </div>
                <p className="mt-1 text-xs text-emerald-700/80">
                  Mot de passe provisoire (à transmettre au livreur) :
                </p>
                <div className="mt-2 flex items-center gap-2">
                  <code className="flex-1 rounded-md bg-white px-3 py-2 text-sm font-mono text-gray-900">
                    {createdPassword.password}
                  </code>
                  <Button size="sm" variant="secondary" onClick={handleCopyPassword} className="shrink-0">
                    {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    {copied ? "Copié" : "Copier"}
                  </Button>
                </div>
              </div>
            )}
          </Card>

          <div className="flex flex-col gap-3">
            {!drivers || drivers.length === 0 ? (
              <EmptyState icon={Truck} title="Aucun livreur" />
            ) : (
              drivers.map((driver) => (
                <Card key={driver.id} className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 font-semibold text-ink">
                      {driver.full_name || driver.email}
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-sm text-muted-foreground">{driver.email}</p>
                      <Badge variant={STATUS_VARIANT[driver.availability_status] ?? "default"}>
                        {STATUS_LABEL[driver.availability_status] ?? driver.availability_status}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {driver.vehicle_type} · {driver.phone || "sans téléphone"}
                      {driver.position_updated_at
                        ? ` · GPS à jour (${new Date(driver.position_updated_at).toLocaleDateString()})`
                        : " · aucune position GPS signalée"}
                    </p>
                  </div>
                </Card>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}