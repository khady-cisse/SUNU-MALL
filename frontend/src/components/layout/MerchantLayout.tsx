import { BarChart3, LayoutDashboard, Megaphone, Package, PlusCircle, Radio, Settings, Store as StoreIcon, Wallet } from "lucide-react";
import { RoleGuard } from "@/components/auth/RoleGuard";
import { MerchantKycGate } from "@/components/kyc/MerchantKycGate";
import type { DashboardNavItem } from "@/components/layout/DashboardShell";

const nav: DashboardNavItem[] = [
  { to: "/merchant", label: "Tableau de bord", icon: <LayoutDashboard className="h-4 w-4" /> },
  { to: "/create-shop", label: "Ma boutique", icon: <StoreIcon className="h-4 w-4" /> },
  { to: "/store-settings", label: "Paramètres", icon: <Settings className="h-4 w-4" /> },
  { to: "/catalog", label: "Catalogue", icon: <Package className="h-4 w-4" /> },
  { to: "/add-product", label: "Ajouter un produit", icon: <PlusCircle className="h-4 w-4" /> },
  { to: "/subscriptions", label: "Abonnements", icon: <Megaphone className="h-4 w-4" /> },
  { to: "/analytics", label: "Analytics", icon: <BarChart3 className="h-4 w-4" /> },
  { to: "/live-sales", label: "Ventes en direct", icon: <Radio className="h-4 w-4" /> },
  { to: "/merchant-wallet", label: "Portefeuille", icon: <Wallet className="h-4 w-4" /> },
];

export function MerchantLayout() {
  return (
    <RoleGuard roles={["merchant"]}>
      <MerchantKycGate nav={nav} title="Espace commerçant" />
    </RoleGuard>
  );
}
