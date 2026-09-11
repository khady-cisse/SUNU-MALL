import { useMemo, useState } from "react";
import { Bell, Megaphone, Send } from "lucide-react";
import * as monetizationApi from "@/api/monetization";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { Textarea } from "@/components/ui/Textarea";
import { useAsync } from "@/hooks/useAsync";
import { formatDate } from "@/lib/utils";

const TARGETS = [
  { value: "", label: "Tous les utilisateurs actifs" },
  { value: "merchant", label: "Vendeurs (merchants)" },
  { value: "client", label: "Clients" },
  { value: "driver", label: "Livreurs (drivers)" },
  { value: "partner", label: "Partenaires" },
  { value: "admin", label: "Administrateurs" },
];

const CHANNELS = [
  { value: "push", label: "In-app (Push)" },
  { value: "email", label: "Email" },
  { value: "sms", label: "SMS" },
];

export default function AdminNotificationsPage() {
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [role, setRole] = useState("");
  const [channel, setChannel] = useState("push");
  const [errors, setErrors] = useState<{ subject?: string; message?: string }>({});
  const [result, setResult] = useState<{ sent: number; role: string } | null>(null);
  const [publishing, setPublishing] = useState(false);

  const {
    data: notifications,
    loading,
    error,
    refetch,
  } = useAsync(() => monetizationApi.listNotifications(), []);

  const broadcasts = useMemo(
    () => (notifications ?? []).filter((n) => n.metadata?.kind === "admin_broadcast"),
    [notifications],
  );

  const targetLabel = (value: string) => TARGETS.find((t) => t.value === value)?.label ?? "";
  const channelLabel = (value: string) => CHANNELS.find((c) => c.value === value)?.label ?? value;

  const handlePublish = async (e: React.FormEvent) => {
    e.preventDefault();
    const nextErrors: { subject?: string; message?: string } = {};
    if (!subject.trim()) nextErrors.subject = "Le sujet est requis.";
    if (!message.trim()) nextErrors.message = "Le message est requis.";
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    setPublishing(true);
    try {
      const res = await monetizationApi.broadcastNotification({
        subject: subject.trim(),
        message: message.trim(),
        role: role || undefined,
        channel,
      });
      setResult(res);
      setSubject("");
      setMessage("");
      refetch();
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div>
      <h1 className="mb-6 flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
        <Megaphone className="h-6 w-6 text-orange" /> Notifications
      </h1>

      <Card className="mb-8">
        <div className="mb-5 flex items-center gap-2">
          <Send className="h-4 w-4 text-orange" />
          <h2 className="font-semibold text-ink">Rédiger et publier une notification</h2>
        </div>
        <form onSubmit={handlePublish} className="flex flex-col gap-4">
          <Input label="Sujet" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Ex : Maintenance prévue samedi soir" error={errors.subject} />
          <Textarea label="Message" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Détail de l'information à diffuser…" rows={4} error={errors.message} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Select label="Destinataires" value={role} onChange={(e) => setRole(e.target.value)}>
              {TARGETS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </Select>
            <Select label="Canal" value={channel} onChange={(e) => setChannel(e.target.value)}>
              {CHANNELS.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex items-center justify-end gap-3">
            {result && (
              <p className="text-sm text-success">
                Publiée : {result.sent} destinataire{result.sent > 1 ? "s" : ""} ({targetLabel(result.role)}).
              </p>
            )}
            <Button type="submit" loading={publishing}>
              <Megaphone className="h-4 w-4" /> Publier
            </Button>
          </div>
        </form>
      </Card>

      <h2 className="mb-3 flex items-center gap-2 font-semibold text-ink">
        <Bell className="h-4 w-4 text-muted-foreground" /> Notifications publiées
      </h2>

      {loading ? (
        <Spinner label="Chargement des notifications…" />
      ) : error ? (
        <ErrorState fullPage onRetry={refetch} />
      ) : broadcasts.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="Aucune notification publiée"
          description="Rédigez un sujet et un message puis cliquez sur Publier pour informer les utilisateurs."
        />
      ) : (
        <div className="flex flex-col gap-3">
          {broadcasts.map((n) => (
            <Card key={n.id} className="flex gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent text-orange">
                <Megaphone className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="truncate font-semibold text-ink">{n.subject}</p>
                  <span className="shrink-0 text-xs text-muted-foreground">{formatDate(n.created_at)}</span>
                </div>
                <p className="mt-0.5 text-sm text-muted-foreground">{n.message}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Badge variant="default">Cible : {targetLabel(n.metadata?.role as string) || "Tous"}</Badge>
                  <Badge variant="success">Canal : {channelLabel(n.channel)}</Badge>
                  <span className="text-xs text-muted-foreground">
                    {String(n.metadata?.recipients ?? "?")} destinataire(s)
                  </span>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}