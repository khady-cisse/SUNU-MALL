import clsx, { type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatPrice(amount: number | string) {
  const value = typeof amount === "string" ? parseFloat(amount) : amount;
  return new Intl.NumberFormat("fr-SN", {
    style: "currency",
    currency: "XOF",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatDate(value: string) {
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

/** Temps de trajet estimé (SSE/API) en libellé lisible, ex. « ~8 min ». */
export function formatEta(seconds: number | null | undefined) {
  if (seconds == null) return null;
  if (seconds <= 0) return "Arrivée imminente";
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  return `~${minutes} min`;
}
