import { useEffect, useState } from "react";
import { CreditCard, Lock } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { type CardDetails, detectBrand, formatCardNumber, formatExpiry } from "./cardValidation";

export function CardPaymentForm({
  onChange,
}: {
  onChange: (card: CardDetails) => void;
}) {
  const [card, setCard] = useState<CardDetails>({ holder: "", number: "", expiry: "", cvc: "" });
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  useEffect(() => {
    onChange(card);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [card]);

  function update<K extends keyof CardDetails>(key: K, value: string) {
    setCard((prev) => ({ ...prev, [key]: value }));
  }

  const brand = detectBrand(card.number);
  const expiryNum = card.expiry.replace("/", "");
  const expired =
    expiryNum.length === 4
      ? Number(expiryNum.slice(2)) < new Date().getFullYear() % 100 ||
        (Number(expiryNum.slice(2)) === new Date().getFullYear() % 100 &&
          Number(expiryNum.slice(0, 2)) < new Date().getMonth() + 1)
      : false;

  return (
    <Card>
      <form className="flex flex-col gap-4" onSubmit={(e) => e.preventDefault()}>
        <div className="flex items-center gap-2">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-accent text-orange">
            <CreditCard className="h-5 w-5" />
          </span>
          <div>
            <p className="font-semibold text-ink">Paiement par carte bancaire</p>
            <p className="text-xs text-muted-foreground">
              {card.number ? `${brand} · ` : ""}transaction sécurisée chiffrée
            </p>
          </div>
        </div>

        <Input
          label="Titulaire de la carte"
          placeholder="Prénom NOM"
          autoComplete="cc-name"
          value={card.holder}
          onChange={(e) => update("holder", e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, holder: true }))}
          error={touched.holder && card.holder.trim().length < 2 ? "Renseignez le nom du titulaire." : undefined}
        />

        <Input
          label="Numéro de carte"
          inputMode="numeric"
          autoComplete="cc-number"
          placeholder="1234 5678 9012 3456"
          value={card.number}
          onChange={(e) => update("number", formatCardNumber(e.target.value))}
          onBlur={() => setTouched((t) => ({ ...t, number: true }))}
          error={touched.number && card.number.replace(/\s/g, "") !== "" && !card.number.replace(/\D/g, "").match(/^\d{13,19}$/) ? "Numéro de carte invalide." : undefined}
        />

        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Expiration"
            inputMode="numeric"
            autoComplete="cc-exp"
            placeholder="MM/AA"
            value={card.expiry}
            onChange={(e) => update("expiry", formatExpiry(e.target.value))}
            onBlur={() => setTouched((t) => ({ ...t, expiry: true }))}
            error={touched.expiry && card.expiry.replace("/", "").length > 0 && expired ? "Carte expirée." : undefined}
          />
          <Input
            label="CVC"
            inputMode="numeric"
            autoComplete="cc-csc"
            placeholder="123"
            maxLength={4}
            value={card.cvc}
            onChange={(e) => update("cvc", e.target.value.replace(/\D/g, "").slice(0, 4))}
            onBlur={() => setTouched((t) => ({ ...t, cvc: true }))}
            error={touched.cvc && card.cvc.length > 0 && card.cvc.length < 3 ? "CVC invalide." : undefined}
          />
        </div>

        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Lock className="h-3.5 w-3.5" />
          Casier de démonstration : aucune donnée de carte n'est réellement transmise.
        </p>
      </form>
    </Card>
  );
}