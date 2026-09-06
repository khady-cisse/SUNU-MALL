import { Link } from "react-router-dom";
import { Store } from "lucide-react";
import { RegisterForm } from "@/components/auth/RegisterForm";

export default function RegisterMerchantPage() {
  return (
    <div>
      <div className="mb-6 flex flex-col items-center gap-3 text-center">
        <span className="grid h-12 w-12 place-items-center rounded-xl bg-accent text-orange">
          <Store className="h-6 w-6" />
        </span>
        <div>
          <h1 className="font-display text-2xl font-extrabold text-gray-900">Ouvrir une boutique</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Créez votre compte commerçant : votre pièce d'identité sera vérifiée avant l'ouverture de votre boutique.
          </p>
        </div>
      </div>
      <RegisterForm role="merchant" />
      <p className="mt-6 border-t border-border pt-5 text-center text-sm text-muted-foreground">
        Déjà un compte ?{" "}
        <Link to="/login" className="font-semibold text-orange transition-colors hover:text-orange-dark">
          Se connecter
        </Link>
      </p>
    </div>
  );
}
