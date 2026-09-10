import { Package } from "lucide-react";
import type { SubscriptionState } from "@/api/monetization";
import { cn } from "@/lib/utils";

/**
 * Bannière de consommation de la limite produits (J'ai X / Y produits).
 * Verdict (limite atteinte / bloqué sans abonnement) calculé par le backend :
 * le frontend affiche uniquement ce que subscription/me/ renvoie.
 */
export function ProductLimitBanner({ account, className }: { account: SubscriptionState | null; className?: string }) {
  if (!account) return null;

  const { product_count, product_limit, is_unlimited, products_remaining } = account;

  if (product_limit === 0 && !account.has_active_subscription) {
    return (
      <div
        className={cn(
          "flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger",
          className,
        )}
      >
        <Package className="h-4 w-4 shrink-0" />
        <p>
          Vous n'avez pas d'abonnement actif : la création de nouveaux produits est suspendue.{" "}
          <span className="font-semibold underline">Passez à une formule</span> pour reprendre.
        </p>
      </div>
    );
  }

  if (is_unlimited) {
    return (
      <div
        className={cn(
          "flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3.5 py-2.5 text-sm text-green-700",
          className,
        )}
      >
        <Package className="h-4 w-4 shrink-0" />
        <p>Produits illimités — {product_count} produit{product_count > 1 ? "s" : ""} publié{product_count > 1 ? "s" : ""}.</p>
      </div>
    );
  }

  const nearLimit = products_remaining != null && products_remaining <= 2;

  return (
    <div className={cn("rounded-lg border px-3.5 py-2.5 text-sm", className, nearLimit ? "border-amber-300 bg-amber-50 text-amber-800" : "border-gray-200 bg-muted/40 text-muted-foreground")}>
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2">
          <Package className="h-4 w-4 shrink-0" />
          <span>
            Produits : <span className="font-semibold">{product_limit == null ? `${product_count} / illimité` : `${product_count} / ${product_limit}`}</span>
            {product_limit != null &&
              (products_remaining === 0 ? " — limite atteinte" : ` — ${products_remaining} restant${(products_remaining ?? 0) > 1 ? "s" : ""}`)}
          </span>
        </p>
      </div>
      {product_limit != null && (
        <progress
          className={cn(
            "mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white [&::-webkit-progress-bar]:bg-white [&::-webkit-progress-value]:rounded-full",
            nearLimit ? "[&::-webkit-progress-value]:bg-danger" : "[&::-webkit-progress-value]:bg-orange",
          )}
          max={product_limit}
          value={product_count}
        />
      )}
    </div>
  );
}