import { useState } from "react";
import { FileText, Download } from "lucide-react";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { apiGet } from "@/lib/api";

const REPORT_TYPES = [
  { key: "global", label: "Rapport global", description: "Vue d'ensemble de la plateforme" },
  { key: "finance", label: "Rapport financier", description: "Commissions, revenus, paiements" },
  { key: "sellers", label: "Rapport vendeurs", description: "Activité par vendeur" },
  { key: "stores", label: "Rapport boutiques", description: "Performance des boutiques" },
  { key: "orders", label: "Rapport commandes", description: "Volume et statuts des commandes" },
  { key: "deliveries", label: "Rapport livraisons", description: "Performance de livraison" },
  { key: "kyc", label: "Rapport KYC", description: "Dossiers de vérification" },
  { key: "complaints", label: "Rapport plaintes", description: "Plaintes et résolutions" },
  { key: "refunds", label: "Rapport remboursements", description: "Historique des remboursements" },
];

export default function AdminReportsPage() {
  const [generating, setGenerating] = useState<string | null>(null);

  const handleExport = async (type: string, format: string) => {
    setGenerating(type);
    try {
      const data = await apiGet<{ url: string }>(`/reports/${type}/?fmt=${format}`);
      window.open(data.url, "_blank");
    } catch {
      // error toast could be added
    } finally {
      setGenerating(null);
    }
  };

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Dashboard", to: "/admin" }, { label: "Rapports" }]} />
      <Card>
        <CardTitle>Rapports & Exports</CardTitle>
        <p className="mt-2 text-sm text-muted-foreground">Générez et téléchargez des rapports détaillés.</p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {REPORT_TYPES.map((report) => (
            <div key={report.key} className="rounded-xl border border-border p-4">
              <div className="flex items-start gap-3">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-orange-50">
                  <FileText className="h-5 w-5 text-orange-600" />
                </div>
                <div className="flex-1">
                  <h3 className="font-medium text-ink">{report.label}</h3>
                  <p className="text-xs text-muted-foreground">{report.description}</p>
                </div>
              </div>
              <div className="mt-4 flex gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  loading={generating === `${report.key}-pdf`}
                  onClick={() => handleExport(report.key, "pdf")}
                >
                  <Download className="h-3 w-3" /> PDF
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={generating === `${report.key}-csv`}
                  onClick={() => handleExport(report.key, "csv")}
                >
                  <Download className="h-3 w-3" /> CSV
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
