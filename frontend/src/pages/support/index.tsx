import { useState } from "react";
import { ChevronDown, CornerDownLeft, Headset, Lock, MessageSquare, Package, Plus, TriangleAlert } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as complaintsApi from "@/api/complaints";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { Textarea } from "@/components/ui/Textarea";
import { cn, formatDate } from "@/lib/utils";
import { formatDateShort } from "@/lib/subscriptions";
import type { SupportTicket, SupportTicketStatus } from "@/types";

const CATEGORIES: { value: string; label: string }[] = [
  { value: "question", label: "Question" },
  { value: "help", label: "Aide / assistance" },
  { value: "account", label: "Problème de compte" },
  { value: "payment", label: "Paiement" },
  { value: "subscription", label: "Abonnement" },
  { value: "tech", label: "Problème technique" },
  { value: "other", label: "Autre" },
];

const STATUS_VARIANT: Record<SupportTicketStatus, "default" | "success" | "warning" | "danger"> = {
  new: "default",
  open: "warning",
  answered: "default",
  resolved: "success",
  closed: "danger",
};

export default function MerchantSupportPage() {
  const [page, setPage] = useState(1);
  const { data, loading, refetch } = useAsync(
    () => complaintsApi.listTickets({ page, page_size: 20 }),
    [page],
  );
  const [createOpen, setCreateOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [replyDraft, setReplyDraft] = useState<string>("");
  const [sendingFor, setSendingFor] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);

  const [category, setCategory] = useState(CATEGORIES[0].value);
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const tickets = data?.results ?? [];
  const totalPages = data ? Math.ceil(data.count / 20) : 0;

  async function handleCreate() {
    if (!subject.trim()) {
      setCreateError("Le sujet est requis.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      await complaintsApi.createTicket({
        category,
        subject: subject.trim(),
        description: description.trim(),
      });
      setCreateOpen(false);
      setSubject("");
      setDescription("");
      if (page !== 1) setPage(1);
      refetch();
    } catch {
      setCreateError("Impossible de créer le ticket.");
    } finally {
      setCreating(false);
    }
  }

  async function sendReply(ticketId: string) {
    const body = replyDraft.trim();
    if (!body) return;
    setSendingFor(ticketId);
    setSendError(null);
    try {
      await complaintsApi.replyToTicket(ticketId, body);
      setReplyDraft("");
      refetch();
    } catch {
      setSendError("Impossible d'envoyer votre message.");
    } finally {
      setSendingFor(null);
    }
  }

  async function closeTicket(ticket: SupportTicket) {
    await complaintsApi.closeTicket(ticket.id);
    refetch();
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="mb-1 flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
            <Headset className="h-6 w-6 text-orange" /> Support & assistance
          </h1>
          <p className="text-sm text-muted-foreground">
            Une question sur votre abonnement, un paiement, un litige ? Ouvrez un ticket — le support vous répond sous 24 h.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" /> Nouveau ticket
        </Button>
      </div>

      {loading ? (
        <Spinner label="Chargement de vos tickets…" />
      ) : tickets.length === 0 ? (
        <Card>
          <EmptyState
            icon={Headset}
            title="Aucun ticket ouvert"
            description="Vos demandes d'assistance apparaîtront ici avec leur référence (TKT-...)."
            action={
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="h-4 w-4" /> Ouvrir un ticket
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {tickets.map((ticket) => {
            const expanded = expandedId === ticket.id;
            return (
              <Card key={ticket.id} className="flex flex-col gap-3">
                <button
                  onClick={() => setExpandedId(expanded ? null : ticket.id)}
                  className="flex flex-wrap items-center justify-between gap-3 text-left"
                >
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-medium text-muted-foreground">{ticket.reference}</span>
                    <span className="truncate font-medium text-ink">{ticket.subject}</span>
                    <Badge variant="default">{CATEGORIES.find((c) => c.value === ticket.category)?.label ?? ticket.category}</Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={STATUS_VARIANT[ticket.status]}>{ticket.status}</Badge>
                    <span className="text-xs text-muted-foreground">{formatDateShort(ticket.created_at)}</span>
                    <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", expanded && "rotate-180")} />
                  </div>
                </button>

                {expanded && (
                  <div className="border-t border-border pt-3">
                    <p className="mb-4 whitespace-pre-wrap text-sm text-muted-foreground">{ticket.description}</p>

                    {ticket.messages.length > 0 && (
                      <div className="mb-4 flex flex-col gap-2">
                        {ticket.messages.map((message) => (
                          <div
                            key={message.id}
                            className={cn(
                              "max-w-[85%] rounded-lg px-3.5 py-2.5 text-sm",
                              message.is_support_reply ? "self-end bg-accent text-ink" : "self-start border border-border text-ink",
                            )}
                          >
                            <div className="mb-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                              {message.is_support_reply ? (
                                <span className="flex items-center gap-1 font-semibold text-orange">
                                  <Lock className="h-3 w-3" /> Support Sunu Mall
                                </span>
                              ) : (
                                <span className="flex items-center gap-1 font-semibold">
                                  <MessageSquare className="h-3 w-3" /> Vous
                                </span>
                              )}
                              <span>{formatDate(message.created_at)}</span>
                            </div>
                            <p className="whitespace-pre-wrap">{message.body}</p>
                          </div>
                        ))}
                      </div>
                    )}

                    {ticket.status !== "closed" && ticket.status !== "resolved" ? (
                      <div className="flex flex-col gap-2">
                        <Textarea
                          rows={3}
                          placeholder="Votre message (précisez toute information utile)…"
                          value={replyDraft}
                          onChange={(e) => setReplyDraft(e.target.value)}
                        />
                        {sendError && (
                          <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
                            <TriangleAlert className="h-4 w-4 shrink-0" />
                            {sendError}
                          </div>
                        )}
                        <div className="flex flex-wrap items-center gap-2">
                          <Button size="sm" onClick={() => sendReply(ticket.id)} loading={sendingFor === ticket.id}>
                            <CornerDownLeft className="h-4 w-4" /> Envoyer la réponse
                          </Button>
                          <Button size="sm" variant="secondary" onClick={() => closeTicket(ticket)}>
                            Clore le ticket
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <p className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Package className="h-3.5 w-3.5" /> Ce ticket est {ticket.status} — ouvrez un nouveau ticket si le problème persiste.
                      </p>
                    )}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Précédent
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} / {totalPages}
          </span>
          <Button size="sm" variant="secondary" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Suivant
          </Button>
        </div>
      )}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Nouveau ticket de support">
        <div className="flex flex-col gap-4">
          <Select label="Catégorie" value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </Select>
          <Input
            label="Sujet"
            placeholder="Ex. : renouvellement d'abonnement"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
          <Textarea
            label="Description"
            rows={4}
            placeholder="Décrivez votre problème le plus précisément possible…"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          {createError && (
            <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
              <TriangleAlert className="h-4 w-4 shrink-0" />
              {createError}
            </div>
          )}
          <Button onClick={handleCreate} loading={creating}>
            Créer le ticket
          </Button>
        </div>
      </Modal>
    </div>
  );
}