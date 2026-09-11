import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ShoppingCart, Trash2 } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as shoppingApi from "@/api/shopping";
import * as catalogApi from "@/api/catalog";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { QuantityStepper } from "@/components/marketplace/QuantityStepper";
import { useCheckoutStore } from "@/store/checkoutStore";
import { useAuthStore } from "@/store/authStore";
import { useCartStore } from "@/store/cartStore";
import { formatPrice } from "@/lib/utils";
import type { Store } from "@/types";

export default function CartPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const { data: cart, loading, refetch } = useAsync(() => (user ? shoppingApi.getCart() : Promise.resolve(null)), [user?.id]);
  const startCheckout = useCheckoutStore((s) => s.startCheckout);
  const updateCartItem = useCartStore((s) => s.updateItem);
  const removeCartItem = useCartStore((s) => s.removeItem);

  const storeIds = useMemo(() => Array.from(new Set((cart?.items ?? []).map((i) => i.store))), [cart]);
  const { data: storesById } = useAsync(async () => {
    const entries = await Promise.all(storeIds.map(async (id) => [id, await catalogApi.getStore(id)] as const));
    return Object.fromEntries(entries) as Record<string, Store>;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeIds.join(",")]);
  const storeName = (storeId: string) => storesById?.[storeId]?.name ?? "Boutique";
  const grandTotal = cart?.items.reduce((sum, i) => sum + i.subtotal, 0) ?? 0;

  async function updateQty(itemId: string, quantity: number) {
    if (quantity < 1) return;
    await updateCartItem(itemId, quantity);
    refetch();
  }

  async function remove(itemId: string) {
    await removeCartItem(itemId);
    refetch();
  }

  function goToCheckout() {
    // Boutique unique : flux classique. Plusieurs boutiques : flux global
    // (storeId = null, les boutiques sont déduites des articles par le backend).
    startCheckout(storeIds.length === 1 ? storeIds[0] : null, storeIds.length === 1 ? storeName(storeIds[0]) : null, cart!.items);
    navigate("/checkout-address");
  }

  if (loading) return <Spinner label="Chargement du panier…" />;

  if (!cart || cart.items.length === 0) {
    return (
      <EmptyState
        icon={ShoppingCart}
        title="Votre panier est vide"
        description="Ajoutez des produits pour préparer votre prochaine commande."
        action={
          <Link to="/search">
            <Button>Découvrir des produits</Button>
          </Link>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold text-gray-900">Mon panier</h1>

      <Card className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
              <th className="py-3 pr-4 font-semibold">Produit</th>
              <th className="py-3 pr-4 font-semibold">Boutique</th>
              <th className="py-3 pr-4 text-center font-semibold">Quantité</th>
              <th className="py-3 pr-4 text-right font-semibold">Sous-total</th>
              <th className="py-3 w-10" aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {cart.items.map((item) => (
              <tr key={item.id} className="border-b border-border last:border-b-0">
                <td className="py-3 pr-4">
                  <p className="font-semibold text-ink">{item.product_name}</p>
                  <p className="text-xs text-muted-foreground">{formatPrice(item.unit_price)} / unité</p>
                </td>
                <td className="py-3 pr-4 text-muted-foreground">{storeName(item.store)}</td>
                <td className="py-3 pr-4 text-center">
                  <QuantityStepper size="sm" value={item.quantity} onChange={(q) => updateQty(item.id, q)} />
                </td>
                <td className="py-3 pr-4 text-right font-semibold text-ink">{formatPrice(item.subtotal)}</td>
                <td className="py-3 text-right">
                  <button
                    onClick={() => remove(item.id)}
                    aria-label={`Retirer ${item.product_name} du panier`}
                    className="focus-ring rounded-full p-2 text-muted-foreground transition-colors hover:bg-red-50 hover:text-danger"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {storeIds.length > 1 ? `${storeIds.length} boutiques dans ce panier — une seule livraison.` : "Une seule boutique dans ce panier."}
        </p>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-xs text-muted-foreground">Total</p>
            <p className="font-display text-xl font-extrabold text-orange">{formatPrice(grandTotal)}</p>
          </div>
          <Button onClick={goToCheckout}>Passer commande</Button>
        </div>
      </div>
    </div>
  );
}
