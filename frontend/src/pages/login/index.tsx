import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Lock, LogIn, Mail, TriangleAlert } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import * as authApi from "@/api/auth";
import { useAuthStore } from "@/store/authStore";
import { roleHomePath } from "@/lib/roles";

const schema = z.object({
  email: z.string().email("Email invalide"),
  password: z.string().min(1, "Mot de passe requis"),
});

type FormValues = z.infer<typeof schema>;

export default function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const loginSuccess = useAuthStore((s) => s.loginSuccess);
  const [serverError, setServerError] = useState<string | null>(null);
  const [needsVerification, setNeedsVerification] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: FormValues) {
    setServerError(null);
    setNeedsVerification(null);
    try {
      const data = await authApi.login(values.email, values.password);
      loginSuccess(data);
      // `next` est une valeur non fiable (variable d'environnement du client) :
      // on refuse toute redirection hors-site (protocole externe ou URL absolue).
      const rawNext = searchParams.get("next");
      const next = rawNext?.startsWith("/") ? rawNext : null;
      navigate(next || roleHomePath(data.user.roles), { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setNeedsVerification(values.email);
      } else if (err instanceof ApiError) {
        const data = err.data as Record<string, unknown>;
        setServerError((data?.error as string) || "Identifiants incorrects.");
      } else {
        setServerError("Impossible de contacter le serveur.");
      }
    }
  }

  return (
    <div>
      <div className="mb-6 flex flex-col items-center gap-3 text-center">
        <span className="grid h-12 w-12 place-items-center rounded-xl bg-accent text-orange">
          <LogIn className="h-6 w-6" />
        </span>
        <div>
          <h1 className="font-display text-2xl font-extrabold text-gray-900">Connexion</h1>
          <p className="mt-1 text-sm text-muted-foreground">Accédez à votre compte Sunu Mall.</p>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <Input
          label="Email"
          type="email"
          placeholder="vous@exemple.com"
          icon={Mail}
          {...register("email")}
          error={errors.email?.message}
        />
        <Input label="Mot de passe" type="password" icon={Lock} {...register("password")} error={errors.password?.message} />

        {serverError && (
          <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
            <TriangleAlert className="h-4 w-4 shrink-0" />
            {serverError}
          </div>
        )}
        {needsVerification && (
          <ResendVerification email={needsVerification} />
        )}

        <Button type="submit" loading={isSubmitting} className="mt-2 w-full">
          Se connecter
        </Button>
      </form>

      <div className="mt-6 flex flex-col gap-1.5 border-t border-border pt-5 text-center text-sm text-muted-foreground">
        <p>
          Pas encore de compte ?{" "}
          <Link to="/register-client" className="font-semibold text-orange transition-colors hover:text-orange-dark">
            Créer un compte client
          </Link>
        </p>
        <p>
          Vous êtes commerçant ?{" "}
          <Link to="/register-merchant" className="font-semibold text-orange transition-colors hover:text-orange-dark">
            Ouvrir une boutique
          </Link>
        </p>
        <p>
          Vous êtes livreur ?{" "}
          <Link to="/driver-login" className="font-semibold text-orange transition-colors hover:text-orange-dark">
            Connexion livreur
          </Link>
        </p>
      </div>
    </div>
  );
}

function ResendVerification({ email }: { email: string }) {
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  async function resend() {
    setLoading(true);
    try {
      await authApi.resendVerification(email);
      setSent(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
      <p className="font-medium">Votre email n'est pas encore vérifié.</p>
      {sent ? (
        <p className="mt-1 font-semibold">Email de vérification renvoyé !</p>
      ) : (
        <button
          type="button"
          onClick={resend}
          disabled={loading}
          className="focus-ring mt-1 font-semibold underline decoration-amber-400 underline-offset-2 disabled:opacity-60"
        >
          {loading ? "Envoi…" : "Renvoyer l'email de vérification"}
        </button>
      )}
    </div>
  );
}
