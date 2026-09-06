import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { CheckCircle2, Lock, Mail, Phone, ShieldCheck, TriangleAlert, User } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import * as authApi from "@/api/auth";

const schema = z.object({
  first_name: z.string().min(1, "Prénom requis"),
  last_name: z.string().min(1, "Nom requis"),
  email: z.string().email("Email invalide"),
  phone: z.string().min(6, "Numéro de téléphone requis"),
  password: z.string().min(8, "8 caractères minimum"),
});

type FormValues = z.infer<typeof schema>;

const DOC_TYPES = [
  { value: "cni", label: "Carte nationale d'identité" },
  { value: "passeport", label: "Passeport" },
  { value: "permis", label: "Permis de conduire" },
  { value: "titre_sejour", label: "Titre de séjour" },
  { value: "autre", label: "Autre document" },
];

export function RegisterForm({ role }: { role: "client" | "merchant" }) {
  const isMerchant = role === "merchant";
  const [serverError, setServerError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [documentType, setDocumentType] = useState("cni");
  const [front, setFront] = useState<File | null>(null);
  const [back, setBack] = useState<File | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      if (!isMerchant) {
        await authApi.register({ ...values, role_name: role });
      } else {
        if (!front || !back) {
          setServerError("Veuillez joindre le recto et le verso de votre pièce d'identité.");
          return;
        }
        const form = new FormData();
        Object.entries(values).forEach(([key, value]) => form.set(key, String(value)));
        form.set("role_name", "merchant");
        form.set("document_type", documentType);
        form.set("document_front", front);
        form.set("document_back", back);
        await authApi.register(form);
      }
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError) {
        const data = err.data as Record<string, unknown>;
        const firstError = Object.values(data ?? {})[0];
        setServerError(Array.isArray(firstError) ? String(firstError[0]) : "Inscription impossible.");
      } else {
        setServerError("Impossible de contacter le serveur.");
      }
    }
  }

  if (done) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl bg-green-50/60 py-8 text-center">
        <span className="grid h-14 w-14 place-items-center rounded-full bg-green-100">
          <CheckCircle2 className="h-8 w-8 text-success" />
        </span>
        <h2 className="font-display text-lg font-bold text-ink">Inscription réussie !</h2>
        {isMerchant ? (
          <p className="max-w-sm text-sm text-muted-foreground">
            Vérifiez votre boîte mail pour activer votre compte, puis notre équipe examinera vos pièces
            d'identité (≤ 24 h) avant l'ouverture de votre boutique.
          </p>
        ) : (
          <p className="max-w-xs text-sm text-muted-foreground">
            Vérifiez votre boîte mail pour activer votre compte avant de vous connecter.
          </p>
        )}
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4">
        <Input label="Prénom" icon={User} {...register("first_name")} error={errors.first_name?.message} />
        <Input label="Nom" icon={User} {...register("last_name")} error={errors.last_name?.message} />
      </div>
      <Input label="Email" type="email" icon={Mail} {...register("email")} error={errors.email?.message} />
      <Input label="Téléphone" icon={Phone} {...register("phone")} error={errors.phone?.message} />
      <Input label="Mot de passe" type="password" icon={Lock} {...register("password")} error={errors.password?.message} />

      {isMerchant && (
        <div className="rounded-xl border border-border bg-muted p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-ink">
            <ShieldCheck className="h-4 w-4 text-orange" />
            Vérification d'identité (obligatoire)
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Fournissez une pièce d'identité officielle au recto et au verso. Sunu Mall vérifie votre identité
            avant l'ouverture de votre boutique (JPG/PNG/PDF, moins de 8 Mo).
          </p>
          <select
            value={documentType}
            onChange={(e) => setDocumentType(e.target.value)}
            className="mt-3 w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-ink outline-none focus:border-orange focus:ring-2 focus:ring-orange/20"
          >
            {DOC_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          <label className="mt-3 block">
            <span className="block text-xs font-semibold text-muted-foreground">Recto de la pièce</span>
            <input
              type="file"
              accept="image/*,application/pdf"
              onChange={(e) => setFront(e.target.files?.[0] ?? null)}
              className="mt-1 block w-full text-sm text-ink"
            />
          </label>
          <label className="mt-3 block">
            <span className="block text-xs font-semibold text-muted-foreground">Verso de la pièce</span>
            <input
              type="file"
              accept="image/*,application/pdf"
              onChange={(e) => setBack(e.target.files?.[0] ?? null)}
              className="mt-1 block w-full text-sm text-ink"
            />
          </label>
        </div>
      )}

      {serverError && (
        <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
          <TriangleAlert className="h-4 w-4 shrink-0" />
          {serverError}
        </div>
      )}

      <Button type="submit" loading={isSubmitting} className="mt-2 w-full">
        {isMerchant ? "Créer mon compte vendeur" : "Créer mon compte"}
      </Button>
    </form>
  );
}