import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { KeyRound, TriangleAlert } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import { changePassword } from "@/api/auth";
import { useAuthStore } from "@/store/authStore";

const schema = z
  .object({
    current_password: z.string().min(1, "Mot de passe actuel requis"),
    new_password: z.string().min(8, "Au moins 8 caractères"),
    confirm_password: z.string().min(1, "Confirmez le nouveau mot de passe"),
  })
  .refine((v) => v.new_password === v.confirm_password, {
    path: ["confirm_password"],
    message: "Les deux mots de passe ne correspondent pas",
  });

type FormValues = z.infer<typeof schema>;

export default function DriverPasswordChangePage() {
  const navigate = useNavigate();
  const updateUser = useAuthStore((s) => s.updateUser);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      await changePassword({
        current_password: values.current_password,
        new_password: values.new_password,
        confirm_password: values.confirm_password,
      });
      updateUser({ must_change_password: false });
      navigate("/driver-dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        const data = Array.isArray(err.data)
          ? (err.data as unknown[]).join(" ")
          : typeof err.data === "string"
            ? err.data
            : err.data && typeof err.data === "object" && "error" in (err.data as Record<string, unknown>)
              ? String((err.data as Record<string, unknown>).error)
              : "Mot de passe actuel incorrect.";
        setServerError(data);
      } else {
        setServerError("Impossible de modifier le mot de passe.");
      }
    }
  }

  return (
    <div>
      <div className="mb-6 flex flex-col items-center gap-3 text-center">
        <span className="grid h-12 w-12 place-items-center rounded-xl bg-gradient-navy text-white shadow-navy-glow">
          <KeyRound className="h-6 w-6" />
        </span>
        <div>
          <h1 className="font-display text-2xl font-extrabold text-gray-900">Changer de mot de passe</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Pour des raisons de sécurité, vous devez définir un nouveau mot de passe avant de commencer.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <Input
          label="Mot de passe actuel"
          type="password"
          {...register("current_password")}
          error={errors.current_password?.message}
        />
        <Input
          label="Nouveau mot de passe"
          type="password"
          {...register("new_password")}
          error={errors.new_password?.message}
        />
        <Input
          label="Confirmer le nouveau mot de passe"
          type="password"
          {...register("confirm_password")}
          error={errors.confirm_password?.message}
        />

        {serverError && (
          <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
            <TriangleAlert className="h-4 w-4 shrink-0" />
            {serverError}
          </div>
        )}

        <Button type="submit" loading={isSubmitting} className="mt-2 w-full">
          Enregistrer le nouveau mot de passe
        </Button>
      </form>
    </div>
  );
}
