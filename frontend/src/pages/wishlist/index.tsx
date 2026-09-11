import { Link } from "react-router-dom";
import { Heart, ImageOff, Trash2 } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as shoppingApi from "@/api/shopping";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/authStore";
import { useWishlistStore } from "@/store/wishlistStore";
import { formatPrice } from "@/lib/utils";

interface WishRow {
  id: string;
  product: string;
  product_name: string;
  product_price: string;
}

export default function WishlistPage() {
  const user = useAuthStore((s) => s.user);
  const guestItems = useWishlistStore((s) => s.guestItems);
  const { data: serverWishlist, loading, error, refetch } = useAsync(
    () => (user ? shoppingApi.getWishlist() : Promise.resolve(null)),
    [user?.id],
  );
  const toggleItem = useWishlistStore((s) => s.toggleItem);

  async function remove(productId: string) {
    await toggleItem(productId);
    refetch();
  }

  const items: WishRow[] = user ? (serverWishlist?.items ?? []) : guestItems;

  if (loading)
    return (
      <div className="mx-auto max-w-7xl px-4 py-6">
        <Spinner label="Chargement de votre wishlist…" />
      </div>
    );

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <h1 className="mb-6 flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
        <Heart className="h-6 w-6 text-orange" /> Ma liste de souhaits
      </h1>
      {error ? (
        <ErrorState fullPage onRetry={refetch} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Heart}
          title="Votre wishlist est vide"
          description="Ajoutez des produits en cliquant sur le cœur depuis le catalogue."
          action={
            <Link to="/search">
              <Button>Découvrir des produits</Button>
            </Link>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <Card key={item.id} variant="interactive" className="flex items-center gap-3">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-lg bg-muted">
                <ImageOff className="h-5 w-5 text-muted-foreground" />
              </span>
              <div className="min-w-0 flex-1">
                <Link to={`/product/${item.product}`} className="truncate font-semibold text-ink transition-colors hover:text-orange">
                  {item.product_name}
                </Link>
                <p className="text-sm font-bold text-orange">{formatPrice(item.product_price)}</p>
              </div>
              <button
                onClick={() => remove(item.product)}
                aria-label="Retirer de la wishlist"
                className="focus-ring rounded-full p-2 text-muted-foreground transition-colors hover:bg-red-50 hover:text-danger"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}