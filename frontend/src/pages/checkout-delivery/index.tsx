import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Bike, ChevronRight, MapPin, Truck, Store as StoreIcon } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import * as ordersApi from "@/api/orders";
import { useCheckoutStore } from "@/store/checkoutStore";
import { formatPrice } from "@/lib/utils";

const OPTIONS = [
  { id: "standard" as const, label: "Livraison standard", eta: "24-48h", icon: Truck },
  { id: "express" as const, label: "Livraison express", eta: "2-4h", icon: Bike },
  { id: "pickup" as const, label: "Retrait en boutique", eta: "Selon disponibilité", icon: StoreIcon },
];

export default function CheckoutDeliveryPage() {
  const navigate = useNavigate();
  const storeId = useCheckoutStore((s) => s.storeId);
  const items = useCheckoutStore((s) => s.items);
  const address = useCheckoutStore((s) => s.address);
  const setDelivery = useCheckoutStore((s) => s.setDelivery);
  const [fees, setFees] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!address) return;
    let cancelled = false;
    const items = useCheckoutStore
      .getState()
      .items.map((i) => ({ product_variant: i.product_variant, quantity: i.quantity }));
    const quoteFor = (delivery_type: "pickup" | "standard" | "express") =>
      storeId
        ? ordersApi.getDeliveryQuote({ store: storeId, address: address.id, delivery_type }).then((fee) => fee)
        : ordersApi.deliveryCalculate({ items, address: address.id, delivery_type }).then((quote) => parseFloat(quote.delivery_fee));
    Promise.all(OPTIONS.map((o) => quoteFor(o.id).then((fee) => [o.id, fee] as const)))
      .then((entries) => {
        if (!cancelled) setFees(Object.fromEntries(entries));
      })
      .catch(() => {
        if (!cancelled) setError("Impossible de calculer les frais de livraison. Veuillez réessayer.");
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId, address]);

  if (items.length === 0) return <Navigate to="/cart" replace />;
  if (!address) return <Navigate to="/checkout-address" replace />;

  function choose(optionId: (typeof OPTIONS)[number]["id"]) {
    setDelivery(optionId, fees?.[optionId] ?? 0);
    navigate("/checkout-payment");
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold text-gray-900">Mode de livraison</h1>
      <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
        <MapPin className="h-4 w-4 text-orange" />
        Livraison à : {address.street}, {address.city}
      </p>
      {!fees ? (
        error ? (
          <div className="rounded-2xl border border-danger/30 bg-red-50 p-4 text-sm text-danger">{error}</div>
        ) : (
          <Spinner label="Calcul des frais de livraison…" />
        )
      ) : (
        <div className="flex flex-col gap-3">
          {OPTIONS.map((option) => {
            const fee = fees[option.id] ?? 0;
            return (
              <button key={option.id} onClick={() => choose(option.id)} className="text-left">
                <Card variant="interactive" className="flex items-center gap-4">
                  <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent text-orange">
                    <option.icon className="h-5 w-5" />
                  </span>
                  <div className="flex-1">
                    <p className="font-semibold text-ink">{option.label}</p>
                    <p className="text-xs text-muted-foreground">{option.eta}</p>
                  </div>
                  <p className="font-bold text-ink">{fee === 0 ? "Gratuit" : formatPrice(fee)}</p>
                  <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" />
                </Card>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
