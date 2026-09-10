import { useMemo, useState } from "react";
import { Check, Megaphone, Plus, Square, TriangleAlert, X } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as catalogApi from "@/api/catalog";
import * as monetizationApi from "@/api/monetization";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import { SponsorProductModal } from "@/components/merchant/SponsorProductModal";
import { Spinner } from "@/components/ui/Spinner";
import { cn, formatPrice } from "@/lib/utils";
import { formatDateShort } from "@/lib/subscriptions";
import type { Product } from "@/types";

const STATUS_VARIANT: Record<string, "sponsored" | "default" | "danger"> = {
  active: "sponsored",
  inactive: "default",
  expired: "danger",
};

export default function PromotionsPage() {
  const { data: sponsorships, loading, refetch } = useAsync(() => monetizationApi.listMySponsoredProducts(), []);
  const { data: own } = useAsync(() => catalogApi.listMyStores(), []);
  const storeId = own?.[0]?.id;

  const { data: myProducts, loading: loadingProducts } = useAsync(
    async () => (storeId ? catalogApi.listAllProductsForStore(storeId) : []),
    [storeId],
  );

  const [pickerOpen, setPickerOpen] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [stoppingId, setStoppingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const productsById = useMemo(
    () => new Map((myProducts ?? []).map((p) => [p.id, p])),
    [myProducts],
  );

  const sponsorable = useMemo(
    () => (myProducts ?? []).filter((p) => p.status === "active"),
    [myProducts],
  );

  if (loading) return <Spinner label="Chargement des promotions…" />;

  async function stop(id: string) {
    setStoppingId(id);
    setError(null);
    try {
      await monetizationApi.stopSponsoredProduct(id);
      refetch();
    } catch {
      setError("Impossible d'arrêter cette campagne.");
    } finally {
      setStoppingId(null);
    }
  }

  async function remove(id: string) {
    if (!confirm("Supprimer cette campagne ?")) return;
    setDeletingId(id);
    setError(null);
    try {
      await monetizationApi.deleteSponsoredProduct(id);
      refetch();
    } catch {
      setError("Impossible de supprimer cette campagne.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="mb-1 flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
            <Megaphone className="h-6 w-6 text-orange" /> Promotions
          </h1>
          <p className="text-sm text-muted-foreground">
            Mettez vos produits en avant : le badge « Sponsorisé » les affiche en tête sur la marketplace pendant la période choisie.
          </p>
        </div>
        <Button onClick={() => setPickerOpen(true)} disabled={sponsorable.length === 0}>
          <Plus className="h-4 w-4" /> Nouvelle campagne
        </Button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
          <TriangleAlert className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {sponsorships?.length === 0 ? (
        <Card>
          <EmptyState
            icon={Megaphone}
            title="Aucune campagne"
            description="Sponsorisez un produit pour gagner en visibilité sur la marketplace."
            action={
              <Button onClick={() => setPickerOpen(true)} disabled={sponsorable.length === 0}>
                <Plus className="h-4 w-4" /> Lancer ma première campagne
              </Button>
            }
          />
        </Card>
      ) : (
        <Card>
          <CardTitle>Mes campagnes</CardTitle>
          <div className="mt-3 flex flex-col gap-3">
            {sponsorships?.map((sponsorship) => {
              const product = productsById.get(sponsorship.product);
              return (
                <div key={sponsorship.id} className="flex flex-wrap items-center justify-between gap-3 border-t border-border py-3 text-sm">
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{product?.name ?? sponsorship.product}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatPrice(sponsorship.daily_budget)}/jour · du {formatDateShort(sponsorship.starts_at)} au {formatDateShort(sponsorship.ends_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant={STATUS_VARIANT[sponsorship.status]}>
                      {sponsorship.status === "active" ? <Check className="h-3 w-3" /> : sponsorship.status === "inactive" ? <Square className="h-3 w-3" /> : <X className="h-3 w-3" />}
                      {sponsorship.status}
                    </Badge>
                    {sponsorship.status === "active" && (
                      <Button size="sm" variant="secondary" loading={stoppingId === sponsorship.id} onClick={() => stop(sponsorship.id)}>
                        Arrêter
                      </Button>
                    )}
                    <Button size="sm" variant="danger" loading={deletingId === sponsorship.id} onClick={() => remove(sponsorship.id)}>
                      Supprimer
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <Modal open={pickerOpen} onClose={() => setPickerOpen(false)} title="Choisir un produit à sponsoriser" size="lg">
        {loadingProducts ? (
          <Spinner label="Chargement des produits…" />
        ) : sponsorable.length === 0 ? (
          <EmptyState icon={Megaphone} title="Aucun produit actif" description="Seuls les produits publiés (statut actif) peuvent être sponsorisés." />
        ) : (
          <div className="flex flex-col gap-2">
            {sponsorable.map((product) => (
              <button key={product.id} onClick={() => setSelectedProduct(product)} className="text-left">
                <Card
                  variant="interactive"
                  className={cn("flex items-center gap-3", selectedProduct?.id === product.id ? "border-orange ring-1 ring-orange" : "")}
                >
                  <span className="grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-lg bg-accent text-orange">
                    {product.images[0]?.url ? (
                      <img src={product.images[0].url} alt={product.name} className="h-full w-full object-cover" />
                    ) : (
                      <Megaphone className="h-4 w-4" />
                    )}
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-ink">{product.name}</p>
                    <p className="text-xs text-muted-foreground">{formatPrice(product.base_price)}</p>
                  </div>
                </Card>
              </button>
            ))}
          </div>
        )}
      </Modal>

      {selectedProduct && (
        <SponsorProductModal
          product={selectedProduct}
          onClose={() => {
            setSelectedProduct(null);
            setPickerOpen(true);
          }}
          onCreated={() => {
            setSelectedProduct(null);
            setPickerOpen(false);
            refetch();
          }}
        />
      )}
    </div>
  );
}