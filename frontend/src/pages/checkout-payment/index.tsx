import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { CheckCircle2, FlaskConical, TriangleAlert, XCircle } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import * as ordersApi from "@/api/orders";
import * as paymentsApi from "@/api/payments";
import { useCheckoutStore } from "@/store/checkoutStore";
import { formatPrice } from "@/lib/utils";
import { apiErrorMessage, ApiError } from "@/lib/api";
import type { CheckoutPayload, GlobalOrder, Order } from "@/types";
import { PAYMENT_METHODS } from "@/lib/paymentMethods";
import { CardPaymentForm } from "@/components/checkout/CardPaymentForm";
import { isCardComplete, type CardDetails } from "@/components/checkout/cardValidation";

const METHODS = PAYMENT_METHODS;

export default function CheckoutPaymentPage() {
  const navigate = useNavigate();
  const { storeId, address, items, deliveryMethod, deliveryFee, paymentMethod, setPaymentMethod, reset } = useCheckoutStore();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdOrder, setCreatedOrder] = useState<Order | GlobalOrder | null>(null);
  const [sandboxMessage, setSandboxMessage] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<"success" | "failed" | null>(null);
  const [paymentFailed, setPaymentFailed] = useState(false);
  const [cardDetails, setCardDetails] = useState<CardDetails>({ holder: "", number: "", expiry: "", cvc: "" });

  useEffect(() => {
    if (createdOrder?.payment) {
      paymentsApi.initiatePayment(createdOrder.payment.id).then((res) => setSandboxMessage(res.message));
    }
  }, [createdOrder]);

  // Une fois la commande créée, ces gardes ne doivent plus s'appliquer :
  // reset() (appelé après un paiement simulé réussi, avant la navigation
  // vers /order-confirmed) vide storeId/address, et sans cette condition
  // le composant se re-rendait entre-temps sur cette page et redirigeait
  // vers /cart avant même que la navigation explicite n'ait eu lieu.
  if (!createdOrder) {
    if (items.length === 0) return <Navigate to="/cart" replace />;
    if (!address) return <Navigate to="/checkout-address" replace />;
  }

  const subtotal = items.reduce((sum, i) => sum + i.subtotal, 0);
  const total = subtotal + deliveryFee;

  async function handleConfirm() {
    setSubmitting(true);
    setError(null);
    try {
      const payload: CheckoutPayload = {
        address: address!.id,
        delivery_type: deliveryMethod,
        payment_method: paymentMethod,
        items: items.map((i) => ({ product_variant: i.product_variant, quantity: i.quantity })),
      };
      // Boutique unique : le store est transmis (commande classique).
      // Panier multi-boutiques : store absent → backend déduit les boutiques
      // des articles et renvoie une GlobalOrder.
      if (storeId) payload.store = storeId;
      const order = await ordersApi.checkout(payload);
      setCreatedOrder(order);
    } catch (err) {
      setError(
        apiErrorMessage(err, err instanceof ApiError ? "Impossible de finaliser la commande." : "Erreur réseau."),
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSandboxOutcome(outcome: "success" | "failed") {
    if (!createdOrder?.payment) return;
    setConfirming(outcome);
    try {
      await paymentsApi.sandboxConfirmPayment(createdOrder.payment.id, outcome);
      if (outcome === "success") {
        const isGlobal = "number_of_stores" in createdOrder;
        reset();
        navigate(isGlobal ? `/order-confirmed?gorder=${createdOrder.id}` : `/order-confirmed?order=${createdOrder.id}`);
      } else {
        setPaymentFailed(true);
      }
    } finally {
      setConfirming(null);
    }
  }

  if (createdOrder) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="font-display text-2xl font-bold text-gray-900">Paiement</h1>
        <Card className="flex flex-col gap-4">
          <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            <FlaskConical className="h-4 w-4 shrink-0" />
            <div>
              <p className="font-semibold">Mode test (sandbox)</p>
              <p>{sandboxMessage ?? "Aucune vraie transaction Wave/Orange Money/carte n'est envoyée."}</p>
            </div>
          </div>

          <p className="text-sm text-muted-foreground">
            Commande n°{createdOrder.id.slice(0, 8)} — <strong>{formatPrice(createdOrder.total_amount)}</strong> via{" "}
            {createdOrder.payment?.method}
          </p>

          {paymentFailed ? (
            <div className="flex flex-col items-center gap-3 py-4 text-center">
              <span className="grid h-14 w-14 place-items-center rounded-full bg-red-100">
                <XCircle className="h-8 w-8 text-danger" />
              </span>
              <p className="text-sm font-medium text-danger">Paiement simulé en échec.</p>
              <Button onClick={() => handleSandboxOutcome("success")} loading={confirming === "success"}>
                Réessayer (simuler succès)
              </Button>
            </div>
          ) : (
            <div className="flex gap-3">
              <Button
                onClick={() => handleSandboxOutcome("success")}
                loading={confirming === "success"}
                className="flex-1"
              >
                <CheckCircle2 className="h-4 w-4" />
                Simuler paiement réussi
              </Button>
              <Button
                variant="secondary"
                onClick={() => handleSandboxOutcome("failed")}
                loading={confirming === "failed"}
              >
                Simuler échec
              </Button>
            </div>
          )}
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold text-gray-900">Paiement</h1>

      <div className="flex flex-col gap-3">
        {METHODS.map((method) => (
          <button key={method.id} onClick={() => setPaymentMethod(method.id)} className="text-left">
            <Card
              variant="interactive"
              className={paymentMethod === method.id ? "border-orange ring-1 ring-orange" : ""}
            >
              <div className="flex items-center gap-4">
                <span className="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-xl bg-accent text-orange">
                  {method.image ? (
                    <img src={method.image} alt={method.label} className="h-full w-full object-cover" />
                  ) : (
                    method.icon && <method.icon className="h-5 w-5" />
                  )}
                </span>
                <p className="font-semibold text-ink">{method.label}</p>
              </div>
            </Card>
          </button>
        ))}
      </div>

      {paymentMethod === "card" && <CardPaymentForm onChange={setCardDetails} />}

      <Card className="flex flex-col gap-2 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Sous-total</span>
          <span>{formatPrice(subtotal)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Livraison</span>
          <span>{deliveryFee === 0 ? "Gratuit" : formatPrice(deliveryFee)}</span>
        </div>
        <div className="flex justify-between border-t border-border pt-2 font-bold text-ink">
          <span>Total</span>
          <span className="text-orange">{formatPrice(total)}</span>
        </div>
      </Card>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
          <TriangleAlert className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      <Button onClick={handleConfirm} loading={submitting} className="w-full" disabled={paymentMethod === "card" && !isCardComplete(cardDetails)}>
        Confirmer et payer {formatPrice(total)}
      </Button>
    </div>
  );
}
