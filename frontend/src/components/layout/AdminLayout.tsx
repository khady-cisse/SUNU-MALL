import { BadgeCheck, BadgeInfo, Banknote, ClipboardList, CreditCard, LayoutDashboard, ShieldCheck, Store as StoreIcon, Users } from "lucide-react";
import { RoleGuard } from "@/components/auth/RoleGuard";
import { DashboardShell, type DashboardNavItem } from "@/components/layout/DashboardShell";

const nav: DashboardNavItem[] = [
  { to: "/admin", label: "Tableau de bord", icon: <LayoutDashboard className="h-4 w-4" /> },
  { to: "/admin-users", label: "Utilisateurs", icon: <Users className="h-4 w-4" /> },
  { to: "/admin-managers", label: "Administrateurs", icon: <ShieldCheck className="h-4 w-4" /> },
  { to: "/admin-shops", label: "Boutiques", icon: <StoreIcon className="h-4 w-4" /> },
  { to: "/admin-orders", label: "Commandes", icon: <ClipboardList className="h-4 w-4" /> },
  { to: "/admin-payments", label: "Paiements", icon: <CreditCard className="h-4 w-4" /> },
  { to: "/admin-finance", label: "Finance", icon: <Banknote className="h-4 w-4" /> },
  { to: "/admin-kyc-sellers", label: "KYC Vendeurs", icon: <BadgeCheck className="h-4 w-4" /> },
  { to: "/admin-kyc-drivers", label: "KYC Livreurs", icon: <BadgeInfo className="h-4 w-4" /> },
];

export function AdminLayout() {
  return (
    <RoleGuard roles={["admin"]}>
      <DashboardShell nav={nav} title="Administration" />
    </RoleGuard>
  );
}
