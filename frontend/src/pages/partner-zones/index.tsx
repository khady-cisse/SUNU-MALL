import { useState } from "react";
import { Check, Clock, ListChecks, MapPin, Pencil, Weight, X } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as partnerApi from "@/api/partner";
import { apiErrorMessage, ApiError } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import type { PartnerZonePricing } from "@/types";

export default function PartnerZonesPage() {
  const { data: zones, loading, error, refetch } = useAsync(() => partnerApi.listPartnerZones(), []);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState({ client_fee: "", partner_cost: "", estimated_delay_minutes: "", max_weight_kg: "", is_available: true });
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function startEdit(zone: PartnerZonePricing) {
    setEditingId(zone.id);
    setErrorMessage(null);
    setDraft({
      client_fee: zone.client_fee,
      partner_cost: zone.partner_cost,
      estimated_delay_minutes: String(zone.estimated_delay_minutes),
      max_weight_kg: zone.max_weight_kg,
      is_available: zone.is_available,
    });
  }

  async function save() {
    if (!editingId) return;
    setSaving(true);
    setErrorMessage(null);
    try {
      await partnerApi.updatePartnerZone(editingId, {
        client_fee: draft.client_fee,
        partner_cost: draft.partner_cost,
        estimated_delay_minutes: parseInt(draft.estimated_delay_minutes, 10) || 0,
        max_weight_kg: draft.max_weight_kg,
        is_available: draft.is_available,
      });
      setEditingId(null);
      refetch();
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? apiErrorMessage(err, "Impossible d'enregistrer le tarif.") : "Impossible d'enregistrer le tarif.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Spinner label="Chargement des zones…" />;
  if (error) return <ErrorState fullPage onRetry={refetch} />;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
          <ListChecks className="h-6 w-6 text-orange" /> Zones & tarifs
        </h1>
        <p className="text-sm text-muted-foreground">
          Le client paie le <strong className="text-ink">tarif client</strong>, vous recevez le{" "}
          <strong className="text-ink">coût partenaire</strong> ; la marge Sunu Mall est calculée automatiquement.
        </p>
      </div>

      {errorMessage && <p className="rounded-lg border border-danger/30 bg-red-50 px-3 py-2 text-sm text-danger">{errorMessage}</p>}

      {!zones || zones.length === 0 ? (
        <EmptyState icon={MapPin} title="Aucune zone tarifée" description="Un administrateur doit configurer vos zones avant que vous puissiez y livrer." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {zones.map((zone) => (
            <Card key={zone.id} className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-2">
                <p className="flex items-center gap-2 font-semibold text-ink">
                  <MapPin className="h-4 w-4 text-orange" /> {zone.zone_name}
                </p>
                {!zone.is_available && <Badge variant="warning">Inactive</Badge>}
              </div>

              {editingId === zone.id ? (
                <>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-medium text-muted-foreground">Tarif client (FCFA)</span>
                    <input
                      type="number"
                      min="0"
                      step="50"
                      className="focus-ring w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink"
                      value={draft.client_fee}
                      onChange={(e) => setDraft((d) => ({ ...d, client_fee: e.target.value }))}
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-medium text-muted-foreground">Coût partenaire (FCFA)</span>
                    <input
                      type="number"
                      min="0"
                      step="50"
                      className="focus-ring w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink"
                      value={draft.partner_cost}
                      onChange={(e) => setDraft((d) => ({ ...d, partner_cost: e.target.value }))}
                    />
                  </label>
                  <div className="grid grid-cols-2 gap-3">
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-medium text-muted-foreground">Délai estimé (min)</span>
                      <input
                        type="number"
                        min="0"
                        className="focus-ring w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink"
                        value={draft.estimated_delay_minutes}
                        onChange={(e) => setDraft((d) => ({ ...d, estimated_delay_minutes: e.target.value }))}
                      />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-medium text-muted-foreground">Poids max (kg)</span>
                      <input
                        type="number"
                        min="0"
                        step="0.5"
                        className="focus-ring w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink"
                        value={draft.max_weight_kg}
                        onChange={(e) => setDraft((d) => ({ ...d, max_weight_kg: e.target.value }))}
                      />
                    </label>
                  </div>
                  <label className="flex items-center gap-2 text-sm text-ink">
                    <input
                      type="checkbox"
                      checked={draft.is_available}
                      onChange={(e) => setDraft((d) => ({ ...d, is_available: e.target.checked }))}
                      className="h-4 w-4 accent-orange-600"
                    />
                    Zone active pour mes livraisons
                  </label>
                  <div className="flex items-center gap-2">
                    <Button size="sm" onClick={save} loading={saving}>
                      <Check className="h-4 w-4" /> Enregistrer
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                      <X className="h-4 w-4" /> Annuler
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div className="rounded-lg bg-muted/50 px-3 py-2">
                      <p className="text-xs text-muted-foreground">Tarif client</p>
                      <p className="font-bold text-ink">{formatPrice(zone.client_fee)}</p>
                    </div>
                    <div className="rounded-lg bg-muted/50 px-3 py-2">
                      <p className="text-xs text-muted-foreground">Coût partenaire</p>
                      <p className="font-bold text-ink">{formatPrice(zone.partner_cost)}</p>
                    </div>
                  </div>
                  <p className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" /> {zone.estimated_delay_minutes} min
                    </span>
                    <span className="flex items-center gap-1">
                      <Weight className="h-3 w-3" /> {zone.max_weight_kg} kg
                    </span>
                    <span className="ml-auto font-semibold text-orange">Marge {formatPrice(zone.margin)}</span>
                  </p>
                  <Button variant="secondary" size="sm" className="self-start" onClick={() => startEdit(zone)}>
                    <Pencil className="h-4 w-4" /> Modifier
                  </Button>
                </>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}