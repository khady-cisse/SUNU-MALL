import { useState } from "react";
import { TriangleAlert, Wallet as WalletIcon, Check } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as commissionsApi from "@/api/commissions";
import * as kycApi from "@/api/kyc";
import { Card, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import { Pagination } from "@/components/ui/Pagination";
import { ApiError } from "@/lib/api";
import { formatDate, formatPrice } from "@/lib/utils";
import { PAYMENT_METHODS } from "@/lib/paymentMethods";
import type { KycStatus } from "@/types";

const PAGE_SIZE = 20;

const PAYOUT_STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  pending: "warning",
  completed: "success",
  rejected: "danger",
};

const PAYOUT_STATUS_LABEL: Record<string, string> = {
  pending: "En attente",
  completed: "Complété",
  rejected: "Rejeté",
};

export default function SellerPayoutsPage() {
  const { data: dashboard, loading: loadingDash, refetch: refetchDash } = useAsync(
    () => commissionsApi.getSellerFinanceDashboard(),
    [],
  );
  const { data: kyc, loading: loadingKyc } = useAsync<{ status: KycStatus } | null>(async () => {
    try {
      return await kycApi.getMySellerKyc();
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  }, []);
  const [page, setPage] = useState(1);
  const { data: result, loading: loadingPayouts, refetch: refetchPayouts } = useAsync(
    () => commissionsApi.listPayouts({ page }),
    [page],
  );

  const wallet = dashboard?.wallet;
  const kycVerified = kyc?.status === "VERIFIED";

  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<"wave" | "orange_money" | "card">("wave");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleCreate() {
    const value = parseFloat(amount);
    if (!value || value <= 0) {
      setError("Saisissez un montant valide.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      await commissionsApi.createPayout(value, method);
      setOpen(false);
      setAmount("");
      setSuccess("Votre demande de retrait a bien été enregistrée. Un administrateur va la traiter.");
      refetchPayouts();
      refetchDash();
    } catch (err) {
      const data = err instanceof ApiError ? (err.data as { error?: string; amount?: string[] }) : null;
      setError(data?.error ?? data?.amount?.[0] ?? "Impossible de créer le retrait.");
    } finally {
      setSubmitting(false);
    }
  }

  const payouts = result?.results ?? [];
  const totalPages = result ? Math.max(1, Math.ceil(result.count / PAGE_SIZE)) : 1;

  if (loadingDash || loadingKyc || loadingPayouts) return <Spinner label="Chargement des retraits…" />;
  if (!dashboard || !wallet) return <ErrorState fullPage />;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="flex items-center gap-2 font-display text-2xl font-bold text-ink">
        <WalletIcon className="h-6 w-6 text-orange" /> Retraits
      </h1>

      {success && (
        <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3.5 py-2.5 text-sm text-green-700">
          <Check className="h-4 w-4 shrink-0" />
          {success}
        </div>
      )}

      <Card className="flex flex-col gap-4">
        <CardTitle>Demander un retrait</CardTitle>
        <div className="grid grid-cols-1 gap-3">
          <p className="text-sm text-muted-foreground">Solde disponible : {formatPrice(wallet.available_balance)}</p>
          {!kycVerified ? (
            <Badge variant="warning">Votre identité (KYC) doit être vérifiée avant de pouvoir retirer vos fonds.</Badge>
          ) : (
            <Button onClick={() => setOpen(true)}>
              <WalletIcon className="h-4 w-4" /> Retirer des fonds
            </Button>
          )}
        </div>
      </Card>

      <Card>
        <CardTitle>Historique des retraits</CardTitle>
        {payouts.length === 0 ? (
          <EmptyState icon={WalletIcon} title="Aucun retrait effectué" />
        ) : (
          <div className="mt-3 flex flex-col gap-3">
            {payouts.map((payout) => (
              <div key={payout.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 text-sm">
                <div>
                  <p className="flex items-center gap-2 font-medium text-ink">
                    {formatPrice(payout.amount)}
                    <span className="text-xs text-muted-foreground">
                      via {PAYMENT_METHODS.find((m) => m.id === payout.method)?.label ?? payout.method}
                    </span>
                  </p>
                  <p className="text-xs text-muted-foreground">{formatDate(payout.created_at)}</p>
                </div>
                <div className="flex items-center gap-2">
                  {payout.reference && <span className="text-xs text-muted-foreground">{payout.reference}</span>}
                  <Badge variant={PAYOUT_STATUS_VARIANT[payout.status]}>{PAYOUT_STATUS_LABEL[payout.status]}</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} className="mt-4" />
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title="Demander un retrait" size="sm">
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            Solde disponible : <span className="font-semibold text-ink">{formatPrice(wallet.available_balance)}</span>
          </p>
          <Input
            label="Montant (FCFA)"
            type="number"
            min={1}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="Ex. 19000"
          />
          <Select label="Moyen de retrait" value={method} onChange={(e) => setMethod(e.target.value as typeof method)}>
            {PAYMENT_METHODS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </Select>
          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
              <TriangleAlert className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}
          <Button onClick={handleCreate} loading={submitting} className="w-full">
            Confirmer le retrait
          </Button>
        </div>
      </Modal>
    </div>
  );
}
