import { type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore, type Role } from "@/store/authStore";
import { roleHomePath } from "@/lib/roles";
import { Spinner } from "@/components/ui/Spinner";

export function RoleGuard({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const hasHydrated = useAuthStore((s) => s.hasHydrated);

  if (!hasHydrated) {
    return <Spinner label="Vérification de l'accès…" />;
  }

  const allowed = !!user && roles.some((role) => user.roles.includes(role));

  if (!allowed) {
    if (!user) {
      return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
    }
    // Utilisateur connecté mais sans le rôle requis : pas de boucle vers
    // /login (qui le renverrait ici pour toujours) — on le ramène chez lui.
    return <Navigate to={roleHomePath(user.roles)} replace />;
  }

  return <>{children}</>;
}
