import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ShoppingCart, Store as StoreIcon, Trash2 } from "lucide-react";
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
import type { CartItem as ApiCartItem, Store } from "@/types";

function groupByStore(items: ApiCartItem[]) {
  const groups = new Map<string, ApiCartItem[]>();
  for (const item of items) {
    const list = groups.get(item.store) ?? [];
    list.push(item);
    groups.set(item.store, list);
  }
  return Array.from(groups.entries());
}

export default function CartPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const { data: cart, loading, refetch } = useAsync(() => (user ? shoppingApi.getCart() : Promise.resolve(null)), [user?.id]);
  const startCheckout = useCheckoutStore((s) => s.startCheckout);
  const fetchCart = useCartStore((s) => s.fetchCart);

  const groups = useMemo(() => groupByStore(cart?.items ?? []), [cart]);
  const storeIds = useMemo(() => groups.map(([storeId]) => storeId), [groups]);
  const { data: storesById } = useAsync(async () => {
    const entries = await Promise.all(storeIds.map(async (id) => [id, await catalogApi.getStore(id)] as const));
    return Object.fromEntries(entries) as Record<string, Store>;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeIds.join(",")]);
  const storeName = (storeId: string) => storesById?.[storeId]?.name ?? "Boutique";
  const grandTotal = cart?.items.reduce((sum, i) => sum + i.subtotal, 0) ?? 0;

  async function updateQty(itemId: string, quantity: number) {
    if (quantity < 1) return;
    await shoppingApi.updateCartItem(itemId, quantity);
    refetch();
    fetchCart();
  }

  async function remove(itemId: string) {
    await shoppingApi.removeCartItem(itemId);
    refetch();
    fetchCart();
  }

  function goToCheckout(storeId: string, items: ApiCartItem[]) {
    startCheckout(storeId, storeName(storeId), items);
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
      {groups.map(([storeId, items]) => {
        const subtotal = items.reduce((sum, i) => sum + i.subtotal, 0);
        return (
          <Card key={storeId} className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <p className="flex items-center gap-2 font-display font-bold text-gray-800">
                <StoreIcon className="h-4 w-4 text-orange" />
                {storeName(storeId)}
              </p>
              <Button size="sm" onClick={() => goToCheckout(storeId, items)}>
                Commander cette boutique
              </Button>
            </div>
            {items.map((item) => (
              <div key={item.id} className="flex items-center gap-3 border-t border-border pt-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-ink">{item.product_name}</p>
                  <p className="text-sm font-bold text-orange">{formatPrice(item.unit_price)}</p>
                </div>
                <QuantityStepper size="sm" value={item.quantity} onChange={(q) => updateQty(item.id, q)} />
                <p className="w-20 shrink-0 text-right text-sm font-semibold text-ink">{formatPrice(item.subtotal)}</p>
                <button
                  onClick={() => remove(item.id)}
                  aria-label="Retirer du panier"
                  className="focus-ring rounded-full p-2 text-muted-foreground transition-colors hover:bg-red-50 hover:text-danger"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            <div className="flex items-center justify-between border-t border-border pt-3 text-sm font-bold text-ink">
              <span>Sous-total</span>
              <span className="text-orange">{formatPrice(subtotal)}</span>
            </div>
          </Card>
        );
      })}
      {groups.length > 1 && (
        <div className="flex items-center justify-between rounded-xl border border-border bg-muted/40 px-5 py-4 text-sm font-bold text-ink">
          <span>Total ({groups.length} boutiques)</span>
          <span className="font-display text-lg text-orange">{formatPrice(grandTotal)}</span>
        </div>
      )}
    </div>
  );
}
