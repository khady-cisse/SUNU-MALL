import { useEffect, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ShoppingCart, Trash2 } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as catalogApi from "@/api/catalog";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { QuantityStepper } from "@/components/marketplace/QuantityStepper";
import { useCheckoutStore } from "@/store/checkoutStore";
import { useAuthStore } from "@/store/authStore";
import { useCartStore } from "@/store/cartStore";
import { useWishlistStore } from "@/store/wishlistStore";
import { useGuestCheckoutStore } from "@/store/guestCheckoutStore";
import { formatPrice } from "@/lib/utils";
import type { CartItem, Store } from "@/types";
import type { GuestCartLine } from "@/store/cartStore";

function toCartItem(g: GuestCartLine): CartItem {
  const unit = parseFloat(g.unit_price) || 0;
  return {
    id: g.id,
    product_variant: g.product_variant,
    product_name: g.product_name,
    unit_price: g.unit_price,
    quantity: g.quantity,
    subtotal: Math.round(unit * g.quantity * 100) / 100,
    added_at: new Date().toISOString(),
    store: g.store,
  };
}

export default function CartPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const cart = useCartStore((s) => s.cart);
  const guestItems = useCartStore((s) => s.guestItems);
  const loading = useCartStore((s) => s.loading);
  const fetchCart = useCartStore((s) => s.fetchCart);
  const updateCartItem = useCartStore((s) => s.updateItem);
  const removeCartItem = useCartStore((s) => s.removeItem);
  const syncCart = useCartStore((s) => s.syncGuestToServer);
  const syncWishlist = useWishlistStore((s) => s.syncGuestToServer);
  const startCheckout = useCheckoutStore((s) => s.startCheckout);
  const openGuestCheckout = useGuestCheckoutStore((s) => s.open);

  useEffect(() => {
    fetchCart();
  }, [fetchCart]);

  const guestCart = useMemo(() => guestItems.map(toCartItem), [guestItems]);
  const cartItems = useMemo(
    () => (user ? (cart?.items ?? []) : guestCart),
    [user, cart, guestCart],
  );

  const storeIds = useMemo(() => Array.from(new Set(cartItems.map((i) => i.store))), [cartItems]);
  const { data: storesById } = useAsync(
    async () => {
      const entries = await Promise.all(storeIds.map(async (id) => [id, await catalogApi.getStore(id)] as const));
      return Object.fromEntries(entries) as Record<string, Store>;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [storeIds.join(",")],
  );
  const storeName = (storeId: string) => storesById?.[storeId]?.name ?? "Boutique";
  const grandTotal = cartItems.reduce((sum, i) => sum + i.subtotal, 0);

  async function updateQty(itemId: string, quantity: number) {
    if (quantity < 1) return;
    await updateCartItem(itemId, quantity);
  }

  async function remove(itemId: string) {
    await removeCartItem(itemId);
  }

  function goToCheckout() {
    // Boutique unique : flux classique. Plusieurs boutiques : flux global
    // (storeId = null, les boutiques sont déduites des articles par le backend).
    const start = (items: CartItem[]) => {
      startCheckout(storeIds.length === 1 ? storeIds[0] : null, storeIds.length === 1 ? storeName(storeIds[0]) : null, items);
      navigate("/checkout-address");
    };
    if (!user) {
      // Visiteur : on crée d'abord le compte invité (silencieusement), on
      // remonte le panier/favoris locaux vers le serveur, puis on continue.
      openGuestCheckout(async () => {
        await syncCart();
        await syncWishlist();
        start(cartItems);
      });
      return;
    }
    start(cartItems);
  }

  if (loading) return <Spinner label="Chargement du panier…" />;

  if (cartItems.length === 0) {
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
            {cartItems.map((item) => (
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