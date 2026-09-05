import { useState } from "react";
import { FileCheck2, ShieldCheck, UploadCloud } from "lucide-react";
import { ApiError } from "@/lib/api";
import { useAsync } from "@/hooks/useAsync";
import * as kycApi from "@/api/kyc";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";
import type { DriverKyc, KycStatus, SellerKyc } from "@/types";

const DOC_TYPES = [
  { value: "cni", label: "Carte nationale d'identité" },
  { value: "passeport", label: "Passeport" },
  { value: "permis", label: "Permis de conduire" },
  { value: "titre_sejour", label: "Titre de séjour" },
  { value: "autre", label: "Autre document" },
];

const STATUS_META: Record<KycStatus, { label: string; variant: "default" | "success" | "warning" | "danger" }> = {
  PENDING: { label: "Vérification en cours", variant: "warning" },
  UNDER_REVIEW: { label: "Examen en cours", variant: "warning" },
  VERIFIED: { label: "Identité vérifiée", variant: "success" },
  REJECTED: { label: "Vérification à refaire", variant: "danger" },
};

const KINDS = {
  seller: {
    label: "Vendeur",
    headline: "Vérification vendeur",
    description:
      "Pour ouvrir votre boutique et commercialiser vos produits, votre identité doit être vérifiée par Sunu Mall.",
    icon: <ShieldCheck className="h-5 w-5" />,
    getMy: kycApi.getMySellerKyc,
    submit: kycApi.submitSellerKyc,
  },
  driver: {
    label: "Livreur",
    headline: "Vérification livreur",
    description:
      "Pour accepter des livraisons et être visible des commerçants, votre identité doit être vérifiée par Sunu Mall.",
    icon: <ShieldCheck className="h-5 w-5" />,
    getMy: kycApi.getMyDriverKyc,
    submit: kycApi.submitDriverKyc,
  },
} as const;

interface Props {
  kind: "seller" | "driver";
}

async function fetchOwn(getMy: () => Promise<unknown>): Promise<SellerKyc | DriverKyc | null> {
  try {
    return (await getMy()) as SellerKyc | DriverKyc;
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export function KycStatusCard({ kind }: Props) {
  const cfg = KINDS[kind];
  const { data, loading, refetch } = useAsync(() => fetchOwn(cfg.getMy), [kind]);

  const [showForm, setShowForm] = useState(false);
  const [documentType, setDocumentType] = useState("cni");
  const [front, setFront] = useState<File | null>(null);
  const [back, setBack] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submitSuccess, setSubmitSuccess] = useState("");

  async function handleSubmit() {
    if (!front || !back) {
      setSubmitError("Veuillez sélectionner les deux faces de la pièce.");
      return;
    }
    setSubmitting(true);
    setSubmitError("");
    setSubmitSuccess("");
    try {
      const form = new FormData();
      form.set("document_type", documentType);
      form.set("document_front", front);
      form.set("document_back", back);
      await cfg.submit(form);
      setSubmitSuccess("Documents envoyés ! La vérification est en cours.");
      setShowForm(false);
      setFront(null);
      setBack(null);
      refetch();
    } catch {
      setSubmitError("L'envoi a échoué. Réessayez ou utilisez des fichiers plus légers (JPG/PNG/PDF, < 8 Mo).");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <Spinner label="Vérification du statut…" />;

  if (!data) {
    return (
      <Card className="flex flex-col gap-3 p-4">
        <div className="flex items-center gap-2">
          {cfg.icon}
          <h2 className="font-display text-lg font-bold text-gray-900">{cfg.headline}</h2>
        </div>
        <p className="text-sm text-muted-foreground">{cfg.description}</p>
        {!showForm ? (
          <div className="flex items-center justify-between gap-3">
            <Badge variant="default">Aucun dossier soumis</Badge>
            <Button size="sm" onClick={() => setShowForm(true)}>
              <UploadCloud className="h-4 w-4" /> Envoyer mes documents
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            <select
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value)}
              className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink outline-none focus:border-orange focus:ring-2 focus:ring-orange/20"
            >
              {DOC_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
            <label className="cursor-pointer">
              <span className="block text-xs font-semibold text-muted-foreground">Recto de la pièce</span>
              <input type="file" accept="image/*,application/pdf" onChange={(e) => setFront(e.target.files?.[0] ?? null)} className="mt-1 block w-full text-sm text-ink" />
            </label>
            <label>
              <span className="block text-xs font-semibold text-muted-foreground">Verso de la pièce</span>
              <input type="file" accept="image/*,application/pdf" onChange={(e) => setBack(e.target.files?.[0] ?? null)} className="mt-1 block w-full text-sm text-ink" />
            </label>
            {submitError && <p className="text-sm text-danger">{submitError}</p>}
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="secondary" onClick={() => setShowForm(false)}>
                Annuler
              </Button>
              <Button size="sm" loading={submitting} onClick={handleSubmit}>
                <UploadCloud className="h-4 w-4" /> Envoyer
              </Button>
            </div>
          </div>
        )}
      </Card>
    );
  }

  const meta = STATUS_META[data.status];
  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-center gap-2">
        {data.status === "VERIFIED" ? (
          <FileCheck2 className="h-5 w-5 text-success" />
        ) : (
          cfg.icon
        )}
        <h2 className="font-display text-lg font-bold text-gray-900">{cfg.headline}</h2>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Badge variant={meta.variant}>{meta.label}</Badge>
        {data.submitted_at && (
          <span className="text-xs text-muted-foreground">Soumis le {formatDate(data.submitted_at)}</span>
        )}
      </div>
      {data.status === "VERIFIED" ? (
        <p className="text-sm text-success">Votre identité a été vérifiée. Toutes les fonctionnalités sont débloquées.</p>
      ) : (
        <p className="text-sm text-muted-foreground">
          {data.status === "REJECTED"
            ? `Notre équipe n'a pas pu valider vos documents : ${data.rejection_reason || "aucun motif indiqué"}.`
            : "Notre équipe vérifie vos documents. Vous recevrez une notification dès la fin de l'examen (≤ 24 h)."}
        </p>
      )}
      {data.status !== "VERIFIED" && (
        <>
          {submitSuccess && <p className="text-sm text-success">{submitSuccess}</p>}
          {!showForm ? (
            <div className="flex justify-end">
              <Button size="sm" variant="secondary" onClick={() => setShowForm(true)}>
                Renvoyer mes documents
              </Button>
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              <select
                value={documentType}
                onChange={(e) => setDocumentType(e.target.value)}
                className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink outline-none focus:border-orange focus:ring-2 focus:ring-orange/20"
              >
                {DOC_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              <label>
                <span className="block text-xs font-semibold text-muted-foreground">Recto de la pièce</span>
                <input type="file" accept="image/*,application/pdf" onChange={(e) => setFront(e.target.files?.[0] ?? null)} className="mt-1 block w-full text-sm text-ink" />
              </label>
              <label>
                <span className="block text-xs font-semibold text-muted-foreground">Verso de la pièce</span>
                <input type="file" accept="image/*,application/pdf" onChange={(e) => setBack(e.target.files?.[0] ?? null)} className="mt-1 block w-full text-sm text-ink" />
              </label>
              {submitError && <p className="text-sm text-danger">{submitError}</p>}
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="secondary" onClick={() => setShowForm(false)}>
                  Annuler
                </Button>
                <Button size="sm" loading={submitting} onClick={handleSubmit}>
                  <UploadCloud className="h-4 w-4" /> Envoyer
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  );
}