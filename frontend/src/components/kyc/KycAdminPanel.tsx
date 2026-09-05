import { useMemo, useState } from "react";
import { FileText, Eye, Store as StoreIcon, Truck, UserRound, XCircle, CheckCircle2 } from "lucide-react";
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
  UNDER_REVIEW: { label: "En cours d'examen", variant: "warning" },
  VERIFIED: { label: "Vérifié", variant: "success" },
  REJECTED: { label: "Rejeté", variant: "danger" },
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
  },
  driver: {
    accountLabel: "Livreur",
    title: "KYC Livreurs",
    icon: <Truck className="h-6 w-6 text-orange" />,
    list: kycApi.listDriverKycs,
    get: kycApi.getDriverKyc,
    approve: kycApi.approveDriverKyc,
    reject: kycApi.rejectDriverKyc,
  },
} as const;

type KycDoc = SellerKyc | DriverKyc;
type Kind = keyof typeof KINDS;

interface Props {
  kind: Kind;
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

export function KycAdminPanel({ kind }: Props) {
  const cfg = KINDS[kind];
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState<string | null>(null);
  const [selected, setSelected] = useState<KycDoc | null>(null);
  const [showConfirmApprove, setShowConfirmApprove] = useState(false);
  const [rejecting, setRejecting] = useState<KycDoc | null>(null);
  const [reason, setReason] = useState("");

  const { data, loading, error, refetch } = useAsync<Paginated<KycDoc>>(
    () => cfg.list({ page }) as Promise<Paginated<KycDoc>>,
    [page, kind],
  );
  const docs = useMemo(() => data?.results ?? [], [data]);
  const totalPages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1;

  const pendingCount = useMemo(() => docs.filter((d) => d.status === "PENDING" || d.status === "UNDER_REVIEW").length, [docs]);

  async function openDetail(doc: KycDoc) {
    try {
      const detail = await cfg.get(doc.id);
      setSelected(detail);
    } catch {
      setSelected(doc);
    }
  }

  async function confirmApprove() {
    if (!selected) return;
    setBusy(selected.id);
    try {
      await cfg.approve(selected.id);
      setShowConfirmApprove(false);
      setSelected(null);
      refetch();
    } finally {
      setBusy(null);
    }
  }

  async function confirmReject() {
    if (!rejecting) return;
    setBusy(rejecting.id);
    try {
      await cfg.reject(rejecting.id, reason);
      setRejecting(null);
      setReason("");
      setSelected(null);
      refetch();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="mb-1 flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
          {cfg.icon} {cfg.title}
        </h1>
        <p className="mb-4 text-sm text-muted-foreground">
          Identité des {cfg.accountLabel.toLowerCase()}s — les pièces sont conservées dans un espace privé et
          consultées via des liens à durée limitée.
        </p>
        {loading ? (
          <Spinner label="Chargement des dossiers…" />
        ) : error ? (
          <ErrorState onRetry={refetch} />
        ) : docs.length === 0 ? (
          <EmptyState icon={FileText} title="Aucun dossier" description="Aucun dossier KYC n'a encore été soumis." />
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
                        {doc.status === "REJECTED" && doc.rejection_reason && (
                          <p className="mt-1 text-xs text-danger">Motif : {doc.rejection_reason}</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {(doc.document_front_url || doc.document_back_url) && (
                        <div className="flex gap-1.5">
                          {doc.document_front_url && (
                            <a href={doc.document_front_url} target="_blank" rel="noreferrer" title="Voir le recto">
                              <img
                                src={doc.document_front_url}
                                alt="Recto de la pièce"
                                className="h-10 w-14 rounded-md border border-border object-cover"
                              />
                            </a>
                          )}
                          {doc.document_back_url && (
                            <a href={doc.document_back_url} target="_blank" rel="noreferrer" title="Voir le verso">
                              <img
                                src={doc.document_back_url}
                                alt="Verso de la pièce"
                                className="h-10 w-14 rounded-md border border-border object-cover"
                              />
                            </a>
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

      {selected && (
        <Modal
          open
          onClose={() => setSelected(null)}
          title={`Examiner le KYC ${cfg.accountLabel.toLowerCase()}`}
          size="lg"
        >
          <KycDetail doc={selected} kind={kind} />
          <div className="mt-5 flex justify-end gap-2">
            {selected.status === "VERIFIED" ? (
              <p className="text-sm font-medium text-green-700">Ce dossier est déjà vérifié.</p>
            ) : (
              <>
                <Button variant="secondary" onClick={() => setRejecting(selected)}>
                  Rejeter
                </Button>
                <Button onClick={() => setShowConfirmApprove(true)}>Approuver</Button>
              </>
            )}
          </div>
        </Modal>
      )}

      {selected && showConfirmApprove && (
        <Modal open onClose={() => setShowConfirmApprove(false)} title="Confirmer la validation ?">
          <p className="text-sm text-ink">
            Vous êtes sur le point de valider l&apos;identité de{" "}
            <strong>{ownerOf(selected).name || ownerOf(selected).email}</strong>. Une fois approuvé, ce compte pourra
            ouvrir une boutique &amp; commercialiser ses produits.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowConfirmApprove(false)}>
              Annuler
            </Button>
            <Button loading={busy === selected.id} onClick={confirmApprove}>
              <CheckCircle2 className="h-4 w-4" /> Valider
            </Button>
          </div>
        </Modal>
      )}

      {rejecting && (
        <Modal open onClose={() => { setRejecting(null); setReason(""); }} title="Rejeter le dossier KYC">
          <p className="text-sm text-ink">
            Motif du rejet pour {ownerOf(rejecting).name || ownerOf(rejecting).email}. Il sera notifié et invité à
            soumettre à nouveau ses documents.
          </p>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="Ex. : photo floue, document illisible…"
            className="mt-3 w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink outline-none focus:border-orange focus:ring-2 focus:ring-orange/20"
          />
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => { setRejecting(null); setReason(""); }}>
              Annuler
            </Button>
            <Button variant="danger" disabled={!reason.trim()} loading={busy === rejecting.id} onClick={confirmReject}>
              <XCircle className="h-4 w-4" /> Rejeter
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
          {doc.document_front_url ? (
            <a href={doc.document_front_url} target="_blank" rel="noreferrer" className="block">
              <img src={doc.document_front_url} alt="Recto de la pièce d'identité" className="w-full rounded-lg border border-border object-cover" />
              <p className="mt-1 text-center text-xs text-muted-foreground">Recto</p>
            </a>
          ) : (
            <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">Recto non fourni</p>
          )}
          {doc.document_back_url ? (
            <a href={doc.document_back_url} target="_blank" rel="noreferrer" className="block">
              <img src={doc.document_back_url} alt="Verso de la pièce d'identité" className="w-full rounded-lg border border-border object-cover" />
              <p className="mt-1 text-center text-xs text-muted-foreground">Verso</p>
            </a>
          ) : (
            <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">Verso non fourni</p>
          )}
        </div>
        {doc.status === "REJECTED" && doc.rejection_reason && (
          <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-danger">Motif du rejet : {doc.rejection_reason}</p>
        )}
      </div>
    </div>
  );
}