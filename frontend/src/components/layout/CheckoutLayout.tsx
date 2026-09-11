import { Outlet, useLocation } from "react-router-dom";
import { Check } from "lucide-react";
import { RoleGuard } from "@/components/auth/RoleGuard";
import { GuestCheckoutModal } from "@/components/auth/GuestCheckoutModal";
import { MarketHeader } from "@/components/layout/MarketHeader";
import { SupportChatWidget } from "@/components/support/SupportChatWidget";
import { cn } from "@/lib/utils";

const STEPS = [
  { path: "/cart", label: "Panier" },
  { path: "/checkout-address", label: "Adresse" },
  { path: "/checkout-delivery", label: "Livraison" },
  { path: "/checkout-payment", label: "Paiement" },
  { path: "/order-confirmed", label: "Confirmation" },
];

function CheckoutStepper({ pathname }: { pathname: string }) {
  const activeIndex = STEPS.findIndex((s) => s.path === pathname);
  if (activeIndex === -1) return null;

  return (
    <div className="border-b border-border bg-muted/40">
      <div className="mx-auto flex max-w-4xl items-center gap-2 px-4 py-4">
        {STEPS.map((step, index) => {
          const isCompleted = index < activeIndex;
          const isActive = index === activeIndex;
          return (
            <div key={step.path} className="flex flex-1 items-center gap-2 last:flex-none">
              <div className="flex flex-col items-center gap-1.5">
                <div
                  className={cn(
                    "grid h-8 w-8 shrink-0 place-items-center rounded-full text-xs font-bold transition-colors",
                    isCompleted && "bg-orange text-white",
                    isActive && "bg-gradient-orange text-white shadow-orange",
                    !isCompleted && !isActive && "bg-white text-muted-foreground border border-border",
                  )}
                >
                  {isCompleted ? <Check className="h-4 w-4" /> : index + 1}
                </div>
                <span
                  className={cn(
                    "hidden text-[11px] font-semibold sm:block",
                    isActive ? "text-orange" : isCompleted ? "text-gray-700" : "text-muted-foreground",
                  )}
                >
                  {step.label}
                </span>
              </div>
              {index < STEPS.length - 1 && (
                <div className={cn("h-0.5 flex-1 rounded-full transition-colors", isCompleted ? "bg-orange" : "bg-border")} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function CheckoutLayout() {
  const { pathname } = useLocation();

  const content = (
    <div className="min-h-screen bg-white">
      <MarketHeader />
      <CheckoutStepper pathname={pathname} />
      <main className="mx-auto max-w-4xl px-4 py-6">
        <Outlet />
      </main>
      <SupportChatWidget />
      <GuestCheckoutModal />
    </div>
  );

  // Le panier reste consultable sans compte : un visiteur y ajoute librement
  // des produits (panier local). Le compte invité n'est créé (silencieusement
  // via GuestCheckoutModal) qu'au moment de « Passer commande ». Les étapes
  // suivantes (adresse, livraison, paiement…) restent protégées.
  if (pathname === "/cart") return content;

  return <RoleGuard roles={["client"]}>{content}</RoleGuard>;
}
