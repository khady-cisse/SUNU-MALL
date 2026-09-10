import { useMemo, useState } from "react";
import {
  Ban,
  CheckCircle2,
  Clock3,
  Eye,
  FileText,
  RotateCcw,
  Store as StoreIcon,
  TriangleAlert,
  Truck,
  UserRound,
  XCircle,
} from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as kycApi from "@/api/kyc";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import { formatDate } from "@/lib/utils";
import type { KycStatus, Paginated, SellerKyc, DriverKyc } from "@/types";

const PAGE_SIZE = 20;

const DOC_TYPE_LABELS: Record<string, string> = {
  cni: "Carte nationale d'identité",
  passeport: "Passeport",
  permis: "Permis de conduire",
  titre_sejour: "Titre de séjour",
  autre: "Autre document",
};

const STATUS_META: Record<KycStatus, { label: string; variant: "default" | "success" | "warning" | "danger" }> = {
  PENDING: { label: "En attente", variant: "default" },
  SUBMITTED: { label: "Reçu", variant: "default" },
  UNDER_REVIEW: { label: "En cours d'examen", variant: "warning" },
  VERIFIED: { label: "Vérifié", variant: "success" },
  REJECTED: { label: "Rejeté", variant: "danger" },
  SUSPENDED: { label: "Suspendu", variant: "warning" },
  BLOCKED: { label: "Bloqué", variant: "danger" },
};

const FILTERS: Array<{ value: "" | KycStatus; label: string }> = [
  { value: "", label: "Tous" },
  { value: "PENDING", label: "En attente" },
  { value: "SUBMITTED", label: "Reçus" },
  { value: "UNDER_REVIEW", label: "En examen" },
  { value: "VERIFIED", label: "Vérifiés" },
  { value: "REJECTED", label: "Rejetés" },
  { value: "SUSPENDED", label: "Suspendus" },
  { value: "BLOCKED", label: "Bloqués" },
];

const FRAUD_FLAG_LABELS: Record<string, string> = {
  document_reused: "Document réutilisé",
  phone_reused: "Téléphone partagé",
};

const KINDS = {
  seller: {
    accountLabel: "Vendeur",
    title: "KYC Vendeurs",
    icon: <StoreIcon className="h-6 w-6 text-orange" />,
    list: kycApi.listSellerKycs,
    get: kycApi.getSellerKyc,
    approve: kycApi.approveSellerKyc,
    reject: kycApi.rejectSellerKyc,
    startReview: kycApi.startReviewSellerKyc,
    resubmit: kycApi.requestResubmissionSellerKyc,
    suspend: kycApi.suspendSellerKyc,
    block: kycApi.blockSellerKyc,
  },
  driver: {
    accountLabel: "Livreur",
    title: "KYC Livreurs",
    icon: <Truck className="h-6 w-6 text-orange" />,
    list: kycApi.listDriverKycs,
    get: kycApi.getDriverKyc,
    approve: kycApi.approveDriverKyc,
    reject: kycApi.rejectDriverKyc,
    startReview: kycApi.startReviewDriverKyc,
    resubmit: kycApi.requestResubmissionDriverKyc,
    suspend: kycApi.suspendDriverKyc,
    block: kycApi.blockDriverKyc,
  },
} as const;

type KycDoc = SellerKyc | DriverKyc;
type Kind = keyof typeof KINDS;

interface Props {
  kind: Kind;
}

interface ReasonAction {
  action: "reject" | "resubmit" | "suspend" | "block";
  title: string;
  prompt: string;
  reasonLabel: string;
  requiresReason: boolean;
  confirmLabel: string;
}

function ownerOf(doc: KycDoc) {
  if ("seller" in doc) {
    return { id: doc.seller, name: doc.seller_name, email: doc.seller_email, phone: doc.seller_phone };
  }
  return { id: doc.driver, name: doc.driver_name, email: doc.driver_email, phone: doc.driver_phone };
}

function shortId(id: string) {
  return id.length > 10 ? `${id.slice(0, 8)}…` : id;
}

/** Un PDF ne se rend pas dans une balise <img> : on l'affiche comme document. */
function isPdfUrl(url: string) {
  return url.toLowerCase().split("?")[0].endsWith(".pdf");
}

function DocumentThumb({ url, alt }: { url: string; alt: string }) {
  if (isPdfUrl(url)) {
    return (
      <a href={url} target="_blank" rel="noreferrer" title={`${alt} (PDF)`}>
        <span className="grid h-10 w-14 place-items-center rounded-md border border-border bg-muted text-orange">
          <FileText className="h-5 w-5" />
        </span>
      </a>
    );
  }
  return (
    <a href={url} target="_blank" rel="noreferrer" title={alt}>
      <img src={url} alt={alt} className="h-10 w-14 rounded-md border border-border object-cover" />
    </a>
  );
}

function DocumentPreview({ url, label }: { url: string | null; label: string }) {
  if (!url) {
    return (
      <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
        {label} non fourni
      </p>
    );
  }
  if (isPdfUrl(url)) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="flex flex-col items-center justify-center gap-2 rounded-lg border border-border bg-muted p-6 text-center transition-colors hover:border-orange/50 hover:bg-orange/5"
      >
        <FileText className="h-9 w-9 text-orange" />
        <p className="text-sm font-semibold text-ink">Voir la pièce ({label})</p>
        <p className="text-xs text-muted-foreground">Document PDF — s&apos;ouvre dans un nouvel onglet</p>
      </a>
    );
  }
  return (
    <a href={url} target="_blank" rel="noreferrer" className="block">
      <img src={url} alt={label} className="w-full rounded-lg border border-border object-cover" />
      <p className="mt-1 text-center text-xs text-muted-foreground">{label}</p>
    </a>
  );
}

function FraudAlert({ doc }: { doc: KycDoc }) {
  if (!("fraud_flags" in doc) || doc.fraud_flags.length === 0) return null;
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm">
      <p className="flex items-center gap-1.5 font-semibold text-danger">
        <TriangleAlert className="h-4 w-4" /> Signaux de fraude
      </p>
      <ul className="mt-1.5 list-inside list-disc space-y-1 text-danger">
        {doc.fraud_flags.map((flag, i) => (
          <li key={i}>
            <span className="font-semibold">{FRAUD_FLAG_LABELS[flag.code] ?? flag.code}</span> — {flag.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

function HistoryBlock({ doc }: { doc: KycDoc }) {
  if (!("history" in doc) || doc.history.length === 0) return null;
  return (
    <div>
      <p className="mb-2 text-xs font-bold uppercase tracking-wide text-muted-foreground">Historique de vérification</p>
      <ol className="space-y-2">
        {doc.history.map((entry, i) => (
          <li key={i} className="rounded-lg bg-muted p-2.5 text-xs text-ink">
            <span className="font-semibold">{STATUS_META[entry.previous_status].label}</span> →{" "}
            <span className="font-semibold">{STATUS_META[entry.new_status].label}</span>
            <span className="text-muted-foreground"> · par {entry.reviewed_by_name || "—"}</span>
            <span className="text-muted-foreground"> · {formatDate(entry.created_at)}</span>
            {entry.reason && <p className="mt-0.5 text-muted-foreground">{entry.reason}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}

export function KycAdminPanel({ kind }: Props) {
  const cfg = KINDS[kind];
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<"" | KycStatus>("");
  const [busy, setBusy] = useState<string | null>(null);
  const [selected, setSelected] = useState<KycDoc | null>(null);
  const [showConfirmApprove, setShowConfirmApprove] = useState(false);
  const [reasonAction, setReasonAction] = useState<ReasonAction | null>(null);
  const [reason, setReason] = useState("");
  const [actionError, setActionError] = useState("");

  const { data, loading, error, refetch } = useAsync<Paginated<KycDoc>>(
    () => cfg.list({ page, status: statusFilter || undefined }) as Promise<Paginated<KycDoc>>,
    [page, statusFilter, kind],
  );
  const docs = useMemo(() => data?.results ?? [], [data]);
  const totalPages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1;

  const pendingCount = useMemo(
    () => docs.filter((d) => d.status === "PENDING" || d.status === "SUBMITTED" || d.status === "UNDER_REVIEW").length,
    [docs],
  );

  function selectFilter(value: "" | KycStatus) {
    setStatusFilter(value);
    setPage(1);
  }

  async function openDetail(doc: KycDoc) {
    try {
      const detail = await cfg.get(doc.id);
      setSelected(detail);
    } catch {
      setSelected(doc);
    }
  }

  function closeDetail() {
    setSelected(null);
    setReasonAction(null);
    setShowConfirmApprove(false);
    setReason("");
    setActionError("");
  }

  async function confirmApprove() {
    if (!selected) return;
    setBusy(selected.id);
    try {
      await cfg.approve(selected.id);
      closeDetail();
      refetch();
    } catch (err) {
      setActionError("La validation a échoué. Réessayez.");
      setBusy(null);
    }
  }

  async function confirmReasonAction() {
    if (!selected || !reasonAction) return;
    setBusy(selected.id);
    setActionError("");
    try {
      const safeReason = reason.trim();
      if (reasonAction.action === "reject") await cfg.reject(selected.id, safeReason);
      else if (reasonAction.action === "resubmit") await cfg.resubmit(selected.id, safeReason);
      else if (reasonAction.action === "suspend") await cfg.suspend(selected.id, safeReason);
      else await cfg.block(selected.id, safeReason);
      closeDetail();
      refetch();
    } catch {
      setActionError("L'action a échoué. Réessayez.");
      setBusy(null);
    }
  }

  function requestAction(action: ReasonAction) {
    setReason("");
    setActionError("");
    setReasonAction(action);
  }

  function startReview() {
    if (!selected) return;
    setBusy(selected.id);
    setActionError("");
    (async () => {
      try {
        await cfg.startReview(selected.id);
        closeDetail();
        refetch();
      } catch {
        setActionError("Impossible de passer en examen. Réessayez.");
        setBusy(null);
      }
    })();
  }

  const effectiveSelected = selected;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="mb-1 flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
          {cfg.icon} {cfg.title}
        </h1>
        <p className="mb-4 text-sm text-muted-foreground">
          Identité des {cfg.accountLabel.toLowerCase()}s — les pièces sont conservées dans un espace privé et consultées
          via des liens à durée limitée.
        </p>

        <div className="mb-4 flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.value || "all"}
              onClick={() => selectFilter(f.value)}
              className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${
                statusFilter === f.value
                  ? "border-orange bg-orange text-white"
                  : "border-border bg-white text-muted-foreground hover:border-orange/40"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {loading ? (
          <Spinner label="Chargement des dossiers…" />
        ) : error ? (
          <ErrorState onRetry={refetch} />
        ) : docs.length === 0 ? (
          <EmptyState icon={FileText} title="Aucun dossier" description="Aucun dossier KYC ne correspond à ce filtre." />
        ) : (
          <>
            <div className="flex flex-col gap-3">
              {docs.map((doc) => {
                const owner = ownerOf(doc);
                const typeLabel = DOC_TYPE_LABELS[doc.document_type] ?? doc.document_type;
                return (
                  <Card key={doc.id} className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent text-orange">
                        {kind === "seller" ? <StoreIcon className="h-5 w-5" /> : <Truck className="h-5 w-5" />}
                      </span>
                      <div>
                        <p className="flex items-center gap-2 font-semibold text-ink">
                          <UserRound className="h-4 w-4 text-muted-foreground" />
                          {owner.name || owner.email}
                          <span className="text-xs font-normal text-muted-foreground">(id {shortId(owner.id)})</span>
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {cfg.accountLabel} · {typeLabel}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Dossier {shortId(doc.id)} · soumis le {doc.submitted_at ? formatDate(doc.submitted_at) : "—"}
                        </p>
                        {(doc.status === "REJECTED" || doc.status === "SUSPENDED" || doc.status === "BLOCKED") &&
                          doc.rejection_reason && (
                            <p className="mt-1 text-xs text-danger">Motif : {doc.rejection_reason}</p>
                          )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {(doc.document_front_url || doc.document_back_url) && (
                        <div className="flex gap-1.5">
                          {doc.document_front_url && (
                            <DocumentThumb url={doc.document_front_url} alt="Recto de la pièce" />
                          )}
                          {doc.document_back_url && (
                            <DocumentThumb url={doc.document_back_url} alt="Verso de la pièce" />
                          )}
                        </div>
                      )}
                      <Badge variant={STATUS_META[doc.status].variant}>{STATUS_META[doc.status].label}</Badge>
                      <Button size="sm" variant="secondary" onClick={() => openDetail(doc)}>
                        <Eye className="h-4 w-4" /> Examiner
                      </Button>
                    </div>
                  </Card>
                );
              })}
            </div>
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} className="mt-4" />
            {pendingCount > 0 && (
              <p className="mt-3 text-sm text-muted-foreground">
                {pendingCount} dossier{pendingCount > 1 ? "s" : ""} en attente d&apos;examen sur cette page.
              </p>
            )}
          </>
        )}
      </div>

      {effectiveSelected && (
        <Modal
          open
          onClose={closeDetail}
          title={`Examiner le KYC ${cfg.accountLabel.toLowerCase()}`}
          size="lg"
        >
          <KycDetail doc={effectiveSelected} kind={kind} />
          {actionError && <p className="mt-3 rounded-lg bg-red-50 p-2 text-sm text-danger">{actionError}</p>}
          <div className="mt-5 flex flex-wrap justify-end gap-2">
            {(["PENDING", "SUBMITTED"] as KycStatus[]).includes(effectiveSelected.status) && (
              <Button variant="secondary" loading={busy === effectiveSelected.id} onClick={startReview}>
                <Clock3 className="h-4 w-4" /> Passer en examen
              </Button>
            )}
            {effectiveSelected.status === "REJECTED" && (
              <Button
                variant="secondary"
                loading={busy === effectiveSelected.id}
                onClick={() =>
                  requestAction({
                    action: "resubmit",
                    title: "Demander une nouvelle soumission",
                    prompt: "Le dossier repassera en REJECTED avec l'annotation « nouvelle soumission ».",
                    reasonLabel: "Ce qui manque au dossier",
                    requiresReason: true,
                    confirmLabel: "Demander la re-soumission",
                  })
                }
              >
                <RotateCcw className="h-4 w-4" /> Nouvelle soumission
              </Button>
            )}
            {!["VERIFIED", "REJECTED", "SUSPENDED", "BLOCKED"].includes(effectiveSelected.status) && (
              <>
                <Button
                  variant="secondary"
                  onClick={() =>
                    requestAction({
                      action: "reject",
                      title: "Rejeter le dossier KYC",
                      prompt: "L'utilisateur sera notifié et invité à soumettre à nouveau ses documents.",
                      reasonLabel: "Motif du rejet",
                      requiresReason: true,
                      confirmLabel: "Rejeter",
                    })
                  }
                >
                  <XCircle className="h-4 w-4" /> Rejeter
                </Button>
                <Button onClick={() => setShowConfirmApprove(true)}>
                  <CheckCircle2 className="h-4 w-4" /> Approuver
                </Button>
              </>
            )}
            {(effectiveSelected.status === "VERIFIED" || effectiveSelected.status === "REJECTED") && (
              <>
                <Button
                  variant="secondary"
                  onClick={() =>
                    requestAction({
                      action: "suspend",
                      title: "Suspendre le compte",
                      prompt: "La vente est momentanément coupée. Le titulaire peut encore fournir des documents.",
                      reasonLabel: "Motif de la suspension (facultatif)",
                      requiresReason: false,
                      confirmLabel: "Suspendre",
                    })
                  }
                >
                  <Clock3 className="h-4 w-4" /> Suspendre
                </Button>
                <Button
                  variant="danger"
                  onClick={() =>
                    requestAction({
                      action: "block",
                      title: "Bloquer le compte",
                      prompt: "La vente est définitivement coupée et aucune nouvelle soumission ne sera acceptée.",
                      reasonLabel: "Motif du blocage (facultatif)",
                      requiresReason: false,
                      confirmLabel: "Bloquer",
                    })
                  }
                >
                  <Ban className="h-4 w-4" /> Bloquer
                </Button>
              </>
            )}
            {effectiveSelected.status === "SUSPENDED" && (
              <Button
                variant="danger"
                onClick={() =>
                  requestAction({
                    action: "block",
                    title: "Bloquer le compte",
                    prompt: "La vente est définitivement coupée et aucune nouvelle soumission ne sera acceptée.",
                    reasonLabel: "Motif du blocage (facultatif)",
                    requiresReason: false,
                    confirmLabel: "Bloquer",
                  })
                }
              >
                <Ban className="h-4 w-4" /> Bloquer
              </Button>
            )}
          </div>
        </Modal>
      )}

      {effectiveSelected && showConfirmApprove && (
        <Modal open onClose={() => setShowConfirmApprove(false)} title="Confirmer la validation ?">
          <p className="text-sm text-ink">
            Vous êtes sur le point de valider l&apos;identité de{" "}
            <strong>{ownerOf(effectiveSelected).name || ownerOf(effectiveSelected).email}</strong>. Une fois approuvé,
            ce compte pourra ouvrir une boutique &amp; commercialiser ses produits.
          </p>
          {actionError && <p className="mt-3 rounded-lg bg-red-50 p-2 text-sm text-danger">{actionError}</p>}
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowConfirmApprove(false)}>
              Annuler
            </Button>
            <Button loading={busy === effectiveSelected.id} onClick={confirmApprove}>
              <CheckCircle2 className="h-4 w-4" /> Valider
            </Button>
          </div>
        </Modal>
      )}

      {effectiveSelected && reasonAction && (
        <Modal open onClose={() => setReasonAction(null)} title={reasonAction.title}>
          <p className="text-sm text-ink">
            {reasonAction.prompt} Dossier de {ownerOf(effectiveSelected).name || ownerOf(effectiveSelected).email}.
          </p>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder={reasonAction.reasonLabel}
            className="mt-3 w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink outline-none focus:border-orange focus:ring-2 focus:ring-orange/20"
          />
          {actionError && <p className="mt-2 rounded-lg bg-red-50 p-2 text-sm text-danger">{actionError}</p>}
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setReasonAction(null)}>
              Annuler
            </Button>
            <Button
              variant={reasonAction.action === "block" ? "danger" : reasonAction.action === "suspend" ? "secondary" : "danger"}
              disabled={reasonAction.requiresReason && !reason.trim()}
              loading={busy === effectiveSelected.id}
              onClick={confirmReasonAction}
            >
              <RotateCcw className="h-4 w-4" /> {reasonAction.confirmLabel}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function KycDetail({ doc, kind }: { doc: KycDoc; kind: Kind }) {
  const cfg = KINDS[kind];
  const owner = ownerOf(doc);
  const typeLabel = DOC_TYPE_LABELS[doc.document_type] ?? doc.document_type;
  const meta = STATUS_META[doc.status];

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg bg-muted p-3 text-sm">
          <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Propriétaire</p>
          <p className="mt-1 font-semibold text-ink">{owner.name || owner.email}</p>
          <p className="text-muted-foreground">{owner.email}</p>
          <p className="text-muted-foreground">{owner.phone || "—"}</p>
          <p className="mt-1 text-xs text-muted-foreground">Utilisateur id : {owner.id}</p>
          {"address" in doc && doc.address && (
            <p className="mt-1 text-xs text-muted-foreground">Adresse déclarée : {doc.address}</p>
          )}
        </div>
        <div className="rounded-lg bg-muted p-3 text-sm">
          <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Dossier</p>
          <p className="mt-1 font-semibold text-ink">KYC {cfg.accountLabel.toLowerCase()}</p>
          <p className="text-muted-foreground">{typeLabel}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Dossier id : {doc.id} · soumis le {doc.submitted_at ? formatDate(doc.submitted_at) : "—"}
          </p>
          <div className="mt-2">
            <Badge variant={meta.variant}>{meta.label}</Badge>
          </div>
        </div>
      </div>
      <div>
        <p className="mb-2 text-xs font-bold uppercase tracking-wide text-muted-foreground">Pièces fournies</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <DocumentPreview url={doc.document_front_url ?? null} label="Recto" />
          <DocumentPreview url={doc.document_back_url ?? null} label="Verso" />
        </div>
        {(doc.status === "REJECTED" || doc.status === "SUSPENDED" || doc.status === "BLOCKED") && doc.rejection_reason && (
          <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-danger">Motif : {doc.rejection_reason}</p>
        )}
      </div>
      <FraudAlert doc={doc} />
      <HistoryBlock doc={doc} />
    </div>
  );
}