import { LayoutDashboard, MapPin, User } from "lucide-react";
import { Navigate, useLocation } from "react-router-dom";
import { RoleGuard } from "@/components/auth/RoleGuard";
import { DashboardShell, type DashboardNavItem } from "@/components/layout/DashboardShell";
import { useAuthStore } from "@/store/authStore";

const nav: DashboardNavItem[] = [
  { to: "/driver-dashboard", label: "Mes courses", icon: <LayoutDashboard className="h-4 w-4" /> },
  { to: "/driver-delivery", label: "Livraison en cours", icon: <MapPin className="h-4 w-4" /> },
  { to: "/driver-profile", label: "Mon profil", icon: <User className="h-4 w-4" /> },
];

function MustChangePasswordGuard({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const { pathname } = useLocation();
  if (user?.must_change_password && pathname !== "/driver-password-change") {
    return <Navigate to="/driver-password-change" replace />;
  }
  return <>{children}</>;
}

export function DriverLayout() {
  return (
    <RoleGuard roles={["driver"]}>
      <MustChangePasswordGuard>
        <DashboardShell nav={nav} title="Espace livreur" />
      </MustChangePasswordGuard>
    </RoleGuard>
  );
}
