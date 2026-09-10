import { useState } from "react";
import { Building2, Check, Copy, KeyRound, ShieldCheck, ShieldOff } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as adminPartnersApi from "@/api/admin-partners";
import { apiErrorMessage } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import type { DeliveryPartner, PartnerStatus } from "@/types";

const STATUS_LABEL: Record<PartnerStatus, string> = {
  active: "Active",
  inactive: "Inactive",
  suspended: "Suspendue",
};

const STATUS_VARIANT: Record<PartnerStatus, "success" | "default" | "danger"> = {
  active: "success",
  inactive: "default",
  suspended: "danger",
};

export default function AdminPartnersPage() {
  const { data: partners, loading, error, refetch } = useAsync(() => adminPartnersApi.listAdminPartners(), []);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [rotatingId, setRotatingId] = useState<string | null>(null);
  const [rawApiKey, setRawApiKey] = useState<{ id: string; key: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    contact_name: "",
    contact_email: "",
    contact_phone: "",
    address: "",
    city: "",
  });

  function update<K extends keyof typeof form>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setCreating(true);
    try {
      await adminPartnersApi.createAdminPartner({
        name: form.name.trim(),
        contact_name: form.contact_name.trim(),
        contact_email: form.contact_email.trim(),
        contact_phone: form.contact_phone.trim(),
        address: form.address.trim(),
        city: form.city.trim(),
      });
      setForm({ name: "", contact_name: "", contact_email: "", contact_phone: "", address: "", city: "" });
      refetch();
    } catch (err) {
      setFormError(apiErrorMessage(err, "Impossible de créer l'entreprise partenaire."));
    } finally {
      setCreating(false);
    }
  }

  async function toggleStatus(partner: DeliveryPartner) {
    setRotatingId(partner.id);
    setActionError(null);
    try {
      if (partner.status === "active") await adminPartnersApi.suspendAdminPartner(partner.id);
      else await adminPartnersApi.activateAdminPartner(partner.id);
      refetch();
    } catch (err) {
      setActionError(apiErrorMessage(err, "Impossible de modifier le statut."));
    } finally {
      setRotatingId(null);
    }
  }

  async function rotate(partner: DeliveryPartner) {
    setRotatingId(partner.id);
    setActionError(null);
    setRawApiKey(null);
    try {
      const result = await adminPartnersApi.rotateAdminPartnerApiKey(partner.id);
      setRawApiKey({ id: partner.id, key: result.api_key });
    } catch (err) {
      setActionError(apiErrorMessage(err, "Impossible de régénérer la clé."));
    } finally {
      setRotatingId(null);
    }
  }

  async function copyKey() {
    if (!rawApiKey) return;
    try {
      await navigator.clipboard.writeText(rawApiKey.key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  if (loading) return <Spinner label="Chargement des partenaires…" />;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="flex flex-col gap-4">
        <h1 className="flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
          <Building2 className="h-6 w-6 text-orange" /> Partenaires logistiques
        </h1>

        {error ? (
          <ErrorState fullPage onRetry={refetch} />
        ) : actionError ? (
          <p className="rounded-lg border border-danger/30 bg-red-50 px-3 py-2 text-sm text-danger">{actionError}</p>
        ) : null}

        {rawApiKey && (
          <Card className="flex flex-col gap-3 border-emerald-500/30 bg-emerald-50">
            <p className="flex items-center gap-2 text-sm font-semibold text-emerald-700">
              <KeyRound className="h-4 w-4" /> Nouvelle clé d'API (affichée une seule fois)
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 break-all rounded-lg border border-dashed border-emerald-300 bg-white px-3 py-2 font-mono text-xs text-gray-900">
                {rawApiKey.key}
              </code>
              <Button size="sm" variant="secondary" onClick={copyKey} className="shrink-0">
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {copied ? "Copié" : "Copier"}
              </Button>
            </div>
          </Card>
        )}

        {!partners || partners.length === 0 ? (
          <EmptyState icon={Building2} title="Aucune entreprise partenaire" description="Créez votre première entreprise à droite." />
        ) : (
          <div className="flex flex-col gap-3">
            {partners.map((partner) => (
              <Card key={partner.id} className="flex flex-col gap-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-ink">{partner.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {partner.contact_name || "—"} · {partner.contact_email || "—"} {partner.contact_phone ? ` · ${partner.contact_phone}` : ""}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {partner.city || "—"} · créée le {formatDate(partner.created_at)}
                    </p>
                  </div>
                  <Badge variant={STATUS_VARIANT[partner.status]}>{STATUS_LABEL[partner.status]}</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  Score qualité : <strong className="text-ink">{partner.score}/100</strong>
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant={partner.status === "active" ? "danger" : "secondary"}
                    onClick={() => toggleStatus(partner)}
                    loading={rotatingId === partner.id}
                  >
                    {partner.status === "active" ? <ShieldOff className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
                    {partner.status === "active" ? "Suspendre" : partner.status === "suspended" ? "Réactiver" : "Activer"}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => rotate(partner)} loading={rotatingId === partner.id}>
                    <KeyRound className="h-4 w-4" />
                    Régénérer la clé API
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      <Card className="h-fit">
        <h2 className="mb-1 font-semibold text-ink">Créer une entreprise partenaire</h2>
        <p className="mb-4 text-xs text-muted-foreground">
          L'entreprise est créée inactive : liez-la ensuite à un compte utilisateur rôle « partenaire », puis activez-la
          et configurez ses zones de livraison.
        </p>

        <form onSubmit={handleCreate} className="flex flex-col gap-4">
          <Input label="Nom de l'entreprise" value={form.name} onChange={(e) => update("name", e.target.value)} required />
          <Input label="Personne de contact" value={form.contact_name} onChange={(e) => update("contact_name", e.target.value)} />
          <Input label="Email de contact" type="email" value={form.contact_email} onChange={(e) => update("contact_email", e.target.value)} />
          <Input label="Téléphone" type="tel" value={form.contact_phone} onChange={(e) => update("contact_phone", e.target.value)} placeholder="+221..." />
          <Input label="Adresse" value={form.address} onChange={(e) => update("address", e.target.value)} />
          <Input label="Ville" value={form.city} onChange={(e) => update("city", e.target.value)} />

          {formError && <p className="rounded-lg border border-danger/30 bg-red-50 px-3 py-2 text-sm text-danger">{formError}</p>}

          <Button type="submit" loading={creating} className="mt-1 self-start">
            Créer l'entreprise
          </Button>
        </form>
      </Card>
    </div>
  );
}