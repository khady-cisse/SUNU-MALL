import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ImagePlus, Megaphone, Package, Pencil, Plus, Trash2, TriangleAlert, Upload } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as catalogApi from "@/api/catalog";
import * as monetizationApi from "@/api/monetization";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { SponsorProductModal } from "@/components/merchant/SponsorProductModal";
import { ApiError } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import { ProductLimitBanner } from "@/components/merchant/ProductLimitBanner";
import type { Product } from "@/types";

const STATUS_VARIANT: Record<Product["status"], "default" | "success" | "warning"> = {
  active: "success",
  draft: "warning",
  inactive: "default",
};

export default function CatalogPage() {
  const { data: own } = useAsync(() => catalogApi.listMyStores(), []);
  const storeIds = (own ?? []).map((s) => s.id);
  const [sponsorTarget, setSponsorTarget] = useState<Product | null>(null);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [publishError, setPublishError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadTargetRef = useRef<string | null>(null);

  const { data: products, loading, refetch } = useAsync(async () => {
    if (storeIds.length === 0) return [];
    const results = await Promise.all(storeIds.map((id) => catalogApi.listAllProductsForStore(id)));
    return results.flat();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeIds.join(",")]);

  const { data: account } = useAsync(() => monetizationApi.getMySubscriptionState(), []);

  const { data: sponsorships, refetch: refetchSponsorships } = useAsync(
    () => monetizationApi.listMySponsoredProducts(),
    [],
  );

  function activeSponsorship(productId: string) {
    return sponsorships?.find((s) => s.product === productId && s.status === "active");
  }

  async function remove(id: string) {
    if (!confirm("Supprimer ce produit ?")) return;
    await catalogApi.deleteProduct(id);
    refetch();
  }

  async function publish(id: string) {
    setPublishError(null);
    try {
      await catalogApi.updateProduct(id, { status: "active" });
      refetch();
    } catch (err) {
      const data = err instanceof ApiError ? (err.data as { detail?: string }) : null;
      setPublishError(data?.detail ?? "Impossible de publier ce produit.");
    }
  }

  async function stopSponsoring(id: string) {
    if (!confirm("Arrêter cette campagne de sponsoring ?")) return;
    await monetizationApi.stopSponsoredProduct(id);
    refetchSponsorships();
  }

  function triggerImageUpload(productId: string) {
    uploadTargetRef.current = productId;
    fileInputRef.current?.click();
  }

  async function handleImageSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    const productId = uploadTargetRef.current;
    e.target.value = "";
    if (!file || !productId) return;
    setUploadingId(productId);
    try {
      await catalogApi.uploadProductImage(productId, file);
      refetch();
    } finally {
      setUploadingId(null);
    }
  }

  async function editPrice(id: string, currentPrice: string) {
    const value = prompt("Nouveau prix (XOF)", currentPrice);
    if (!value) return;
    const price = Number(value);
    if (Number.isNaN(price) || price <= 0) return;
    await catalogApi.updateProduct(id, { base_price: String(price) });
    refetch();
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold text-gray-900">Mon catalogue</h1>
        <Link to="/add-product">
          <Button>
            <Plus className="h-4 w-4" /> Ajouter un produit
          </Button>
        </Link>
      </div>

      <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleImageSelected} />

      <ProductLimitBanner account={account} />

      {publishError && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
          <TriangleAlert className="h-4 w-4 shrink-0" />
          {publishError}
        </div>
      )}

      {loading ? (
        <Spinner label="Chargement du catalogue…" />
      ) : products?.length === 0 ? (
        <EmptyState
          icon={Package}
          title="Aucun produit publié pour le moment"
          description="Ajoutez votre premier produit pour commencer à vendre."
          action={
            <Link to="/add-product">
              <Button>Ajouter un produit</Button>
            </Link>
          }
        />
      ) : (
        <div className="flex flex-col gap-3">
          {products?.map((product) => {
            const sponsorship = activeSponsorship(product.id);
            return (
              <Card key={product.id} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => triggerImageUpload(product.id)}
                    disabled={uploadingId === product.id}
                    className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-lg border border-border bg-muted"
                    title="Changer la photo"
                  >
                    {uploadingId === product.id ? (
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-orange border-t-transparent" />
                    ) : product.images[0]?.url ? (
                      <img src={product.images[0].url} alt={product.name} className="h-full w-full object-cover" />
                    ) : (
                      <ImagePlus className="h-5 w-5 text-muted-foreground" />
                    )}
                  </button>
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-ink">{product.name}</p>
                      {sponsorship && <Badge variant="sponsored">Sponsorisé</Badge>}
                    </div>
                    <p className="text-sm text-muted-foreground">{formatPrice(product.base_price)}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant={STATUS_VARIANT[product.status]}>{product.status}</Badge>
                  {product.status === "draft" && (
                    <button
                      onClick={() => publish(product.id)}
                      className="flex items-center gap-1.5 rounded-full bg-orange/10 px-3 py-1.5 text-xs font-semibold text-orange hover:bg-orange/20"
                    >
                      <Upload className="h-3.5 w-3.5" /> Publier
                    </button>
                  )}
                  <button
                    onClick={() => (sponsorship ? stopSponsoring(sponsorship.id) : setSponsorTarget(product))}
                    className={`rounded-full p-2 hover:bg-muted ${sponsorship ? "text-orange" : "text-muted-foreground"}`}
                    aria-label={sponsorship ? "Arrêter le sponsoring" : "Sponsoriser ce produit"}
                    title={sponsorship ? "Arrêter le sponsoring" : "Sponsoriser ce produit"}
                  >
                    <Megaphone className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => editPrice(product.id, product.base_price)}
                    className="rounded-full p-2 text-muted-foreground hover:bg-muted"
                    aria-label="Modifier le prix"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => remove(product.id)}
                    className="rounded-full p-2 text-muted-foreground hover:bg-muted"
                    aria-label="Supprimer"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {sponsorTarget && (
        <SponsorProductModal
          product={sponsorTarget}
          onClose={() => setSponsorTarget(null)}
          onCreated={refetchSponsorships}
        />
      )}
    </div>
  );
}
