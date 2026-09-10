import { useState } from "react";
import { ChevronDown, ChevronUp, FileText, Wallet } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as partnerApi from "@/api/partner";
import { formatDate, formatPrice } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import type { PartnerInvoice } from "@/types";

const INVOICE_STATUS_LABEL: Record<string, string> = {
  draft: "Brouillon",
  pending: "En attente de paiement",
  paid: "Payée",
  contested: "Contestée",
};

const INVOICE_STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  draft: "default",
  pending: "warning",
  paid: "success",
  contested: "danger",
};

function InvoiceRow({ invoice }: { invoice: PartnerInvoice }) {
  const [open, setOpen] = useState(false);
  return (
    <Card className="flex flex-col gap-3">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between gap-3 text-left">
        <div className="min-w-0">
          <p className="font-semibold text-ink">{invoice.reference}</p>
          <p className="text-xs text-muted-foreground">
            {formatDate(invoice.period_start)} → {formatDate(invoice.period_end)}
            {invoice.due_date ? ` · échéance le ${formatDate(invoice.due_date)}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="text-right">
            <p className="text-sm font-bold text-ink">{formatPrice(invoice.total_due)}</p>
            {invoice.balance !== "0" && <p className="text-xs text-muted-foreground">solde {formatPrice(invoice.balance)}</p>}
          </div>
          <Badge variant={INVOICE_STATUS_VARIANT[invoice.status] ?? "default"}>{INVOICE_STATUS_LABEL[invoice.status] ?? invoice.status}</Badge>
          {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </div>
      </button>

      {open && (
        <div className="flex flex-col gap-2 border-t border-border pt-3 text-sm">
          <div className="grid grid-cols-2 gap-2">
            <p className="text-muted-foreground">Livraisons marketplace</p>
            <p className="text-right font-semibold text-ink">
              {invoice.marketplace_deliveries_count} · {formatPrice(invoice.marketplace_amount)}
            </p>
            <p className="text-muted-foreground">Livraisons à la demande</p>
            <p className="text-right font-semibold text-ink">
              {invoice.on_demand_deliveries_count} · {formatPrice(invoice.on_demand_amount)}
            </p>
            <p className="text-muted-foreground">Frais de recouvrement</p>
            <p className="text-right font-semibold text-ink">{formatPrice(invoice.collection_fees)}</p>
            <p className="font-semibold text-ink">Total dû</p>
            <p className="text-right font-bold text-ink">{formatPrice(invoice.total_due)}</p>
          </div>
          <div className="flex flex-wrap items-center gap-3 border-t border-border pt-2 text-xs text-muted-foreground">
            <span>Commissions : {invoice.marketplace_rate}% / {invoice.on_demand_rate}%</span>
            {invoice.recon_date && <span>· Rappel émis le {formatDate(invoice.recon_date)}</span>}
            {invoice.paid_at && <span>· Payée le {formatDate(invoice.paid_at)}</span>}
          </div>
        </div>
      )}
    </Card>
  );
}

export default function PartnerFinancesPage() {
  const { data: invoices, loading, error, refetch } = useAsync(() => partnerApi.listPartnerInvoices(), []);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
        <Wallet className="h-6 w-6 text-orange" /> Finances & factures
      </h1>

      {loading ? (
        <Spinner label="Chargement des factures…" />
      ) : error ? (
        <ErrorState fullPage onRetry={refetch} />
      ) : !invoices || invoices.length === 0 ? (
        <EmptyState icon={FileText} title="Aucune facture" description="Vos factures mensuelles de livraison apparaîtront ici." />
      ) : (
        <div className="flex flex-col gap-3">
          {invoices.map((invoice) => (
            <InvoiceRow key={invoice.id} invoice={invoice} />
          ))}
        </div>
      )}
    </div>
  );
}