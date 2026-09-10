import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { BadgeCheck, CheckCircle2, Heart, ImageOff, MessageSquare, PackageX, ShoppingCart, TriangleAlert } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as catalogApi from "@/api/catalog";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Textarea } from "@/components/ui/Textarea";
import { Spinner } from "@/components/ui/Spinner";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { EmptyState } from "@/components/ui/EmptyState";
import { StarRating } from "@/components/ui/StarRating";
import { QuantityStepper } from "@/components/marketplace/QuantityStepper";
import { ProductRail } from "@/components/marketplace/ProductRail";
import { useAuthStore } from "@/store/authStore";
import { useGuestCheckoutStore } from "@/store/guestCheckoutStore";
import { useRecentlyViewedStore } from "@/store/recentlyViewedStore";
import { useCartStore } from "@/store/cartStore";
import { useWishlistStore } from "@/store/wishlistStore";
import { ApiError } from "@/lib/api";
import { cn, formatDate, formatPrice } from "@/lib/utils";

export default function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const openGuestCheckout = useGuestCheckoutStore((s) => s.open);
  const addRecentlyViewed = useRecentlyViewedStore((s) => s.addProduct);
  const addCartItem = useCartStore((s) => s.addItem);
  const isFav = useWishlistStore((s) => s.has(id ?? ""));
  const toggleFavorite = useWishlistStore((s) => s.toggleItem);
  const [selectedVariant, setSelectedVariant] = useState<string | null>(null);
  const [activeImage, setActiveImage] = useState(0);
  const [quantity, setQuantity] = useState(1);
  const [adding, setAdding] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [newRating, setNewRating] = useState(0);
  const [newComment, setNewComment] = useState("");
  const [submittingReview, setSubmittingReview] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const { data: product, loading } = useAsync(() => catalogApi.getProduct(id!), [id]);
  const { data: reviews, refetch: refetchReviews } = useAsync(
    () => (id ? catalogApi.listReviews(id) : Promise.resolve([])),
    [id],
  );
  const { data: similarProducts, loading: loadingSimilar } = useAsync(
    () => (id ? catalogApi.listSimilarProducts(id) : Promise.resolve([])),
    [id],
  );

  useEffect(() => {
    if (product) addRecentlyViewed(product.id);
  }, [product, addRecentlyViewed]);

  if (loading)
    return (
      <div className="mx-auto max-w-7xl px-4 py-6">
        <Spinner label="Chargement du produit…" />
      </div>
    );
  if (!product)
    return (
      <div className="mx-auto max-w-7xl px-4 py-8">
        <EmptyState icon={PackageX} title="Produit introuvable" description="Ce produit n'existe pas ou a été retiré de la vente." />
      </div>
    );

  const variant = product.variants.find((v) => v.id === selectedVariant) ?? product.variants[0];
  const images = product.images;
  const image = images[activeImage]?.url ?? images[0]?.url;
  const isAvailable = variant?.is_available ?? false;

  const averageRating = reviews && reviews.length > 0 ? reviews.reduce((sum, r) => sum + r.rating, 0) / reviews.length : 0;
  const hasReviewed = !!user && !!reviews?.some((r) => r.user === user.id);

  async function addToCart() {
    if (!variant) return;
    setAdding(true);
    setFeedback(null);
    try {
      await addCartItem(variant.id, quantity);
      setFeedback({ type: "success", text: "Ajouté au panier !" });
    } catch {
      setFeedback({ type: "error", text: "Impossible d'ajouter au panier." });
    } finally {
      setAdding(false);
    }
  }

  function handleAddToCart() {
    if (!user) {
      openGuestCheckout(addToCart);
      return;
    }
    addToCart();
  }

  async function handleAddToWishlist() {
    if (!user) {
      navigate(`/login?next=/product/${id}`);
      return;
    }
    try {
      await toggleFavorite(product!.id);
      setFeedback({ type: "success", text: isFav ? "Retiré de la wishlist." : "Ajouté à la wishlist !" });
    } catch {
      setFeedback({ type: "error", text: "Impossible de mettre à jour la wishlist." });
    }
  }

  async function handleSubmitReview() {
    if (!user) {
      navigate(`/login?next=/product/${id}`);
      return;
    }
    if (!id || newRating === 0) return;
    setSubmittingReview(true);
    setReviewError(null);
    try {
      await catalogApi.createReview({ product: id, rating: newRating, comment: newComment });
      setNewRating(0);
      setNewComment("");
      refetchReviews();
    } catch (err) {
      if (err instanceof ApiError) {
        const data = err.data as Record<string, unknown>;
        const firstError = Object.values(data ?? {})[0];
        setReviewError(Array.isArray(firstError) ? String(firstError[0]) : "Impossible d'envoyer votre avis.");
      } else {
        setReviewError("Impossible de contacter le serveur.");
      }
    } finally {
      setSubmittingReview(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-8">
      <Breadcrumbs items={[{ label: product.store_name }, { label: product.name }]} />

      <div className="grid gap-8 md:grid-cols-2">
        <div className="flex flex-col gap-3">
          <div className="relative grid aspect-square place-items-center overflow-hidden rounded-2xl bg-muted">
            {image ? (
              <img src={image} alt={product.name} className="h-full w-full object-cover" />
            ) : (
              <ImageOff className="h-12 w-12 text-muted-foreground" />
            )}
            {!isAvailable && variant && (
              <span className="absolute left-3 top-3 rounded-md bg-gray-700 px-2.5 py-1 text-xs font-bold text-white shadow">
                Rupture de stock
              </span>
            )}
          </div>
          {images.length > 1 && (
            <div className="flex gap-2">
              {images.map((img, i) => (
                <button
                  key={img.id}
                  onClick={() => setActiveImage(i)}
                  className={cn(
                    "focus-ring h-16 w-16 shrink-0 overflow-hidden rounded-lg border-2 bg-muted transition-colors",
                    i === activeImage ? "border-orange" : "border-transparent hover:border-border",
                  )}
                >
                  {img.url ? (
                    <img src={img.url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <div className="grid h-full w-full place-items-center">
                      <ImageOff className="h-4 w-4 text-muted-foreground" />
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex flex-col gap-4">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground">
            {product.store_name}
            {product.store_is_verified && <BadgeCheck className="h-4 w-4 text-green-600" aria-label="Vendeur vérifié" />}
          </p>
          <h1 className="font-display text-2xl font-extrabold leading-tight text-gray-900 md:text-3xl">{product.name}</h1>
          {reviews && reviews.length > 0 && (
            <div className="flex items-center gap-2">
              <StarRating value={averageRating} size="sm" />
              <span className="text-sm text-muted-foreground">
                {averageRating.toFixed(1)} · {reviews.length} avis
              </span>
            </div>
          )}
          <p className="font-display text-3xl font-extrabold text-orange">{formatPrice(variant?.price ?? product.base_price)}</p>
          <p className="text-sm leading-relaxed text-ink/80">{product.description || "Aucune description fournie."}</p>

          {product.variants.length > 1 && (
            <div>
              <p className="mb-2 text-sm font-semibold text-ink">Variante</p>
              <div className="flex flex-wrap gap-2">
                {product.variants.map((v) => (
                  <button
                    key={v.id}
                    onClick={() => setSelectedVariant(v.id)}
                    className={cn(
                      "focus-ring rounded-lg border px-3 py-1.5 text-sm font-semibold transition-colors",
                      variant?.id === v.id ? "border-orange bg-accent text-orange" : "border-border text-ink hover:border-orange/50",
                    )}
                  >
                    {v.sku}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <p className="mb-2 text-sm font-semibold text-ink">Quantité</p>
            <QuantityStepper value={quantity} onChange={setQuantity} max={variant?.quantity ?? 99} disabled={!isAvailable} />
          </div>

          <div className="mt-2 flex gap-3">
            <Button onClick={handleAddToCart} loading={adding} disabled={!variant || !isAvailable} className="flex-1">
              <ShoppingCart className="h-4 w-4" />
              {isAvailable ? "Ajouter au panier" : "Indisponible"}
            </Button>
            <Button
              variant="secondary"
              onClick={handleAddToWishlist}
              aria-label={isFav ? "Retirer de la wishlist" : "Ajouter à la wishlist"}
              aria-pressed={isFav}
            >
              <Heart className={cn("h-4 w-4", isFav && "fill-orange text-orange")} />
            </Button>
          </div>

          {feedback && (
            <div
              className={cn(
                "flex items-center gap-2 rounded-lg border px-3.5 py-2.5 text-sm font-medium",
                feedback.type === "success" ? "border-green-200 bg-green-50 text-green-700" : "border-danger/30 bg-red-50 text-danger",
              )}
            >
              {feedback.type === "success" ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <TriangleAlert className="h-4 w-4 shrink-0" />}
              {feedback.text}
            </div>
          )}
          {!variant && (
            <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
              <TriangleAlert className="h-4 w-4 shrink-0" />
              Ce produit n'a pas encore de variante disponible.
            </div>
          )}
        </div>
      </div>

      <Card className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 font-semibold text-ink">
          <MessageSquare className="h-4 w-4 text-orange" /> Avis clients
          {reviews && reviews.length > 0 && <span className="text-sm font-normal text-muted-foreground">({reviews.length})</span>}
        </h2>

        {user && !hasReviewed && (
          <div className="flex flex-col gap-3 border-b border-border pb-4">
            <p className="text-sm font-semibold text-ink">Laisser un avis</p>
            <StarRating value={newRating} onChange={setNewRating} />
            <Textarea
              placeholder="Votre avis sur ce produit (optionnel)"
              value={newComment}
              onChange={(e) => setNewComment(e.target.value)}
              rows={2}
            />
            {reviewError && (
              <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
                <TriangleAlert className="h-4 w-4 shrink-0" />
                {reviewError}
              </div>
            )}
            <Button onClick={handleSubmitReview} loading={submittingReview} disabled={newRating === 0} className="self-start">
              Envoyer mon avis
            </Button>
          </div>
        )}

        {!reviews || reviews.length === 0 ? (
          <EmptyState icon={MessageSquare} title="Aucun avis pour le moment" description="Soyez le premier à donner votre avis sur ce produit." />
        ) : (
          <div className="flex flex-col gap-4">
            {reviews.map((review) => (
              <div key={review.id} className="flex flex-col gap-1 border-t border-border pt-4 first:border-t-0 first:pt-0">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-ink">{review.user_name}</p>
                  <span className="text-xs text-muted-foreground">{formatDate(review.created_at)}</span>
                </div>
                <StarRating value={review.rating} size="sm" />
                {review.comment && <p className="text-sm text-ink/80">{review.comment}</p>}
              </div>
            ))}
          </div>
        )}
      </Card>

      <ProductRail title="Produits similaires" products={similarProducts} loading={loadingSimilar} />
    </div>
  );
}
