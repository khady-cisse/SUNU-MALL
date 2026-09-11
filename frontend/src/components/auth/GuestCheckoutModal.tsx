import { useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Mail, Phone, TriangleAlert, User } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import * as authApi from "@/api/auth";
import { useAuthStore } from "@/store/authStore";
import { useGuestCheckoutStore } from "@/store/guestCheckoutStore";
import { ApiError } from "@/lib/api";

const schema = z.object({
  first_name: z.string().min(1, "Prénom requis"),
  last_name: z.string().optional(),
  phone: z.string().min(6, "Téléphone requis"),
  email: z.string().email("Email invalide"),
});
type FormValues = z.infer<typeof schema>;

export function GuestCheckoutModal() {
  const { isOpen, pendingAction, close } = useGuestCheckoutStore();
  const loginSuccess = useAuthStore((s) => s.loginSuccess);
  const [conflict, setConflict] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  function handleClose() {
    reset();
    setConflict(false);
    close();
  }

  async function onSubmit(values: FormValues) {
    setConflict(false);
    try {
      const data = await authApi.guestCheckout(values);
      loginSuccess(data);
      await pendingAction?.();
      reset();
      close();
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setConflict(true);
      }
    }
  }

  return (
    <Modal open={isOpen} onClose={handleClose} title="Vos coordonnées" size="sm">
      <p className="mb-4 text-sm text-muted-foreground">
        Pas besoin de créer un compte pour l'instant — juste de quoi vous livrer et vous confirmer votre commande.
      </p>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-3">
        <Input label="Prénom" icon={User} {...register("first_name")} error={errors.first_name?.message} />
        <Input label="Nom (optionnel)" {...register("last_name")} />
        <Input label="Téléphone" icon={Phone} {...register("phone")} error={errors.phone?.message} />
        <Input label="Email" type="email" icon={Mail} {...register("email")} error={errors.email?.message} />

        {conflict && (
          <div className="flex items-start gap-2 rounded-lg border border-danger/30 bg-red-50 px-3.5 py-2.5 text-sm text-danger">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              Cet email est déjà associé à un compte.{" "}
              <Link to="/login" onClick={handleClose} className="font-semibold underline">
                Connectez-vous
              </Link>{" "}
              pour continuer.
            </span>
          </div>
        )}

        <Button type="submit" loading={isSubmitting} className="mt-2 w-full">
          Continuer
        </Button>
      </form>
    </Modal>
  );
}
