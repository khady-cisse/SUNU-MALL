export interface CardDetails {
  holder: string;
  number: string;
  expiry: string;
  cvc: string;
}

/** Valide un numéro de carte avec l'algorithme de Luhn. */
function luhnValid(num: string): boolean {
  const digits = num.replace(/\s|-/g, "");
  if (!/^\d{13,19}$/.test(digits)) return false;
  let sum = 0;
  let double = false;
  for (let i = digits.length - 1; i >= 0; i--) {
    let d = Number(digits[i]);
    if (double) {
      d *= 2;
      if (d > 9) d -= 9;
    }
    sum += d;
    double = !double;
  }
  return sum % 10 === 0;
}

/** Indique si tous les champs de la carte sont remplis et valides. */
export function isCardComplete(card: CardDetails): boolean {
  return (
    card.holder.trim().length > 1 &&
    luhnValid(card.number) &&
    card.expiry.replace("/", "").length === 4 &&
    card.cvc.length >= 3
  );
}

/** Formate "1234567890123456" -> "1234 5678 9012 3456". */
export function formatCardNumber(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 19);
  return digits.replace(/(.{4})/g, "$1 ").trim();
}

/** Formate "1125" -> "11/25" (MM/AA). */
export function formatExpiry(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 4);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)}/${digits.slice(2)}`;
}

/** Détecte la marque de la carte (Visa / Mastercard / autre). */
export function detectBrand(number: string): string {
  const digits = number.replace(/\D/g, "");
  if (/^4/.test(digits)) return "Visa";
  if (/^(5[1-5]|2221|2720)/.test(digits)) return "Mastercard";
  return "Carte";
}
