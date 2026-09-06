import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Lock, Mail, Truck, TriangleAlert } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import * as authApi from "@/api/auth";
import { useAuthStore } from "@/store/authStore";

const schema = z.object({
  email: z.string().email("Email invalide"),
  password: z.string().min(1, "Mot de passe requis"),
});

type FormValues = z.infer<typeof schema>;

export default function DriverLoginPage() {
  const navigate = useNavigate();
  const loginSuccess = useAuthStore((s) => s.loginSuccess);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      const data = await authApi.login(values.email, values.password);
      if (!data.user.roles.includes("driver")) {
        setServerError("Ce compte n'est pas un compte livreur.");
        return;
      }
      loginSuccess(data);
      navigate(
        data.user.must_change_password ? "/driver-password-change" : "/driver-dashboard",
        { replace: true },
      );
    } catch (err) {
      setServerError(err instanceof ApiError ? "Identifiants incorrects." : "Impossible de contacter le serveur.");
    }
  }

  return (
    <div>
      <div className="mb-6 flex flex-col items-center gap-3 text-center">
        <span className="grid h-12 w-12 place-items-center rounded-xl bg-gradient-navy text-white shadow-navy-glow">
          <Truck className="h-6 w-6" />
        </span>
        <div>
          <h1 className="font-display text-2xl font-extrabold text-gray-900">Connexion livreur</h1>
          <p className="mt-1 text-sm text-muted-foreground">Connectez-vous pour consulter vos courses assignées.</p>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <Input label="Email" type="email" icon={Mail} {...register("email")} error={errors.email?.message} />
        <Input label="Mot de passe" type="password" icon={Lock} {...register("password")} error={errors.password?.message} />

        {serverError && (
          <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
            <TriangleAlert className="h-4 w-4 shrink-0" />
            {serverError}
          </div>
        )}

        <Button type="submit" loading={isSubmitting} className="mt-2 w-full">
          Se connecter
        </Button>
      </form>
    </div>
  );
}
