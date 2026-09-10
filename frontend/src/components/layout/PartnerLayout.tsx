import { LayoutDashboard, MapPin, Truck, Wallet, ListChecks, User } from "lucide-react";
import { RoleGuard } from "@/components/auth/RoleGuard";
import { DashboardShell, type DashboardNavItem } from "@/components/layout/DashboardShell";

const nav: DashboardNavItem[] = [
  { to: "/partner", label: "Tableau de bord", icon: <LayoutDashboard className="h-4 w-4" /> },
  { to: "/partner-deliveries", label: "Livraisons", icon: <MapPin className="h-4 w-4" /> },
  { to: "/partner-drivers", label: "Mes livreurs", icon: <Truck className="h-4 w-4" /> },
  { to: "/partner-zones", label: "Zones & tarifs", icon: <ListChecks className="h-4 w-4" /> },
  { to: "/partner-finances", label: "Finances & factures", icon: <Wallet className="h-4 w-4" /> },
  { to: "/partner-profile", label: "Mon entreprise", icon: <User className="h-4 w-4" /> },
];

export function PartnerLayout() {
  return (
    <RoleGuard roles={["partner"]}>
      <DashboardShell nav={nav} title="Espace partenaire" />
    </RoleGuard>
  );
}