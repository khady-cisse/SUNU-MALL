import { useState, useEffect, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  LayoutDashboard, Users, ShieldCheck, Store as StoreIcon, Package, Tag,
  ClipboardList, CreditCard, Banknote, RefreshCw, Truck, MapPin,
  AlertTriangle, Headphones, Bell, Search as SearchIcon,
  BarChart3, FileText, Lock, BadgeCheck, BadgeInfo, Settings, Activity,
  Flame, Flag, Wrench, Database, Zap, PanelLeftClose, PanelLeft,
  Building2, LogOut,
} from "lucide-react";
import { RoleGuard } from "@/components/auth/RoleGuard";
import { NotificationBell } from "@/components/layout/NotificationBell";
import { GlobalSearchModal } from "@/components/admin/GlobalSearchModal";
import { useAuthStore } from "@/store/authStore";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    title: "GÉNÉRAL",
    items: [
      { to: "/admin", label: "Tableau de bord", icon: <LayoutDashboard className="h-4 w-4" /> },
      { to: "/admin-search", label: "Recherche avancée", icon: <SearchIcon className="h-4 w-4" /> },
    ],
  },
  {
    title: "MARKETPLACE",
    items: [
      { to: "/admin-users", label: "Utilisateurs", icon: <Users className="h-4 w-4" /> },
      { to: "/admin-sellers", label: "Vendeurs", icon: <StoreIcon className="h-4 w-4" /> },
      { to: "/admin-shops", label: "Boutiques", icon: <StoreIcon className="h-4 w-4" /> },
      { to: "/admin-products", label: "Produits", icon: <Package className="h-4 w-4" /> },
      { to: "/admin-categories", label: "Catégories", icon: <Tag className="h-4 w-4" /> },
    ],
  },
  {
    title: "COMMERCE",
    items: [
      { to: "/admin-orders", label: "Commandes", icon: <ClipboardList className="h-4 w-4" /> },
      { to: "/admin-payments", label: "Paiements", icon: <CreditCard className="h-4 w-4" /> },
      { to: "/admin-subscriptions", label: "Abonnements", icon: <Banknote className="h-4 w-4" /> },
      { to: "/admin-refunds", label: "Remboursements", icon: <RefreshCw className="h-4 w-4" /> },
    ],
  },
  {
    title: "LIVRAISON",
    items: [
      { to: "/admin-drivers", label: "Livreurs", icon: <Truck className="h-4 w-4" /> },
      { to: "/admin-deliveries", label: "Livraisons", icon: <MapPin className="h-4 w-4" /> },
      { to: "/admin-partners", label: "Partenaires logistiques", icon: <Building2 className="h-4 w-4" /> },
    ],
  },
  {
    title: "SUPPORT",
    items: [
      { to: "/admin-complaints", label: "Plaintes & Litiges", icon: <AlertTriangle className="h-4 w-4" /> },
      { to: "/admin-support", label: "Tickets support", icon: <Headphones className="h-4 w-4" /> },
      { to: "/admin-notifications", label: "Notifications", icon: <Bell className="h-4 w-4" /> },
    ],
  },
  {
    title: "ADMINISTRATION",
    items: [
      { to: "/admin-managers", label: "Administrateurs", icon: <ShieldCheck className="h-4 w-4" /> },
      { to: "/admin-kyc-sellers", label: "KYC Vendeurs", icon: <BadgeCheck className="h-4 w-4" /> },
      { to: "/admin-kyc-drivers", label: "KYC Livreurs", icon: <BadgeInfo className="h-4 w-4" /> },
      { to: "/admin-security", label: "Sécurité & Audit", icon: <Lock className="h-4 w-4" /> },
    ],
  },
  {
    title: "ANALYTIQUE",
    items: [
      { to: "/admin-analytics", label: "Analytics", icon: <BarChart3 className="h-4 w-4" /> },
      { to: "/admin-reports", label: "Rapports", icon: <FileText className="h-4 w-4" /> },
    ],
  },
  {
    title: "TECHNIQUE",
    items: [
      { to: "/admin-monitoring", label: "Monitoring", icon: <Activity className="h-4 w-4" /> },
      { to: "/admin-incidents", label: "Incidents", icon: <Flame className="h-4 w-4" /> },
      { to: "/admin-logs", label: "Logs", icon: <FileText className="h-4 w-4" /> },
      { to: "/admin-deployments", label: "Déploiements", icon: <Database className="h-4 w-4" /> },
      { to: "/admin-feature-flags", label: "Feature Flags", icon: <Flag className="h-4 w-4" /> },
      { to: "/admin-maintenance", label: "Maintenance", icon: <Wrench className="h-4 w-4" /> },
      { to: "/admin-backups", label: "Backups", icon: <Database className="h-4 w-4" /> },
      { to: "/admin-emergency", label: "Emergency Recovery", icon: <Zap className="h-4 w-4" /> },
    ],
  },
];

const SIDEBAR_WIDTH = 260;
const SIDEBAR_COLLAPSED_WIDTH = 68;

export function AdminLayout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { pathname } = useLocation();
  const initials = `${user?.first_name?.[0] ?? ""}${user?.last_name?.[0] ?? ""}`.toUpperCase() || "?";

  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("admin-sidebar-collapsed") === "true");
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem("admin-sidebar-collapsed", String(collapsed));
  }, [collapsed]);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const activeLabel = NAV_GROUPS.flatMap((g) => g.items).find((i) => i.to === pathname)?.label ?? "Administration";

  const renderNav = (isCollapsed: boolean) => (
    <nav className="flex-1 overflow-y-auto px-2 py-2">
      {NAV_GROUPS.map((group) => (
        <div key={group.title} className="mb-2">
          {!isCollapsed && (
            <p className="mb-1 px-3 pt-3 text-[10px] font-bold uppercase tracking-widest text-white/40">
              {group.title}
            </p>
          )}
          {isCollapsed && <div className="mx-auto my-2 h-px w-6 bg-white/10" />}
          {group.items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isCollapsed && "justify-center px-2",
                  isActive
                    ? "bg-white/15 text-white"
                    : "text-white/70 hover:bg-white/10 hover:text-white",
                )
              }
              title={isCollapsed ? item.label : undefined}
            >
              {item.icon}
              {!isCollapsed && <span className="truncate">{item.label}</span>}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  );

  return (
    <RoleGuard roles={["admin"]}>
      <GlobalSearchModal />
      <div className="min-h-screen bg-muted">
        {/* Desktop sidebar */}
        <aside
          className="fixed inset-y-0 left-0 z-30 hidden flex-col navy-panel transition-all duration-200 md:flex"
          style={{ width: collapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH }}
        >
          <div className={cn("flex items-center gap-3 p-4", collapsed && "justify-center")}>
            {!collapsed && (
              <span className="font-display text-lg font-bold text-white">Sunu Mall</span>
            )}
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="ml-auto rounded p-1 text-white/50 hover:bg-white/10 hover:text-white"
              title={collapsed ? "Développer" : "Réduire"}
            >
              {collapsed ? <PanelLeft className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
            </button>
          </div>
          {renderNav(collapsed)}
          <div className={cn("border-t border-white/10 p-3", collapsed && "flex flex-col items-center")}>
            <button
              onClick={logout}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-white/70 transition-colors hover:bg-white/10",
                collapsed && "justify-center px-2",
              )}
              title="Déconnexion"
            >
              <LogOut className="h-4 w-4" />
              {!collapsed && <span>Déconnexion</span>}
            </button>
          </div>
        </aside>

        {/* Mobile overlay */}
        {mobileOpen && (
          <div className="fixed inset-0 z-40 bg-black/40 md:hidden" onClick={() => setMobileOpen(false)} />
        )}
        <aside
          className={cn(
            "fixed inset-y-0 left-0 z-50 flex w-64 flex-col navy-panel transition-transform duration-200 md:hidden",
            mobileOpen ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <div className="flex items-center justify-between p-4">
            <span className="font-display text-lg font-bold text-white">Sunu Mall</span>
            <button onClick={() => setMobileOpen(false)} className="rounded p-1 text-white/50 hover:bg-white/10 hover:text-white">
              &times;
            </button>
          </div>
          {renderNav(false)}
          <div className="border-t border-white/10 p-3">
            <button
              onClick={logout}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-white/70 transition-colors hover:bg-white/10"
            >
              <LogOut className="h-4 w-4" />
              Déconnexion
            </button>
          </div>
        </aside>

        {/* Main content */}
        <div
          className="flex flex-col transition-all duration-200"
          style={{ marginLeft: collapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH }}
        >
          {/* Mobile header */}
          <header className="flex items-center justify-between border-b border-border bg-white px-4 py-3 md:hidden">
            <button onClick={() => setMobileOpen(true)} className="rounded p-1 text-muted-foreground hover:bg-muted">
              <Settings className="h-5 w-5" />
            </button>
            <span className="font-display text-sm font-bold">Administration</span>
            <NotificationBell />
          </header>

          {/* Desktop header */}
          <header className="hidden items-center justify-between gap-4 border-b border-border bg-white px-6 py-4 md:flex">
            <h1 className="font-display text-lg font-bold text-gray-800">{activeLabel}</h1>
            <div className="flex items-center gap-3">
              <button
                onClick={() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }))}
                className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted"
              >
                <SearchIcon className="h-4 w-4" />
                <span className="hidden lg:inline">Rechercher...</span>
                <kbd className="ml-2 hidden rounded border border-border bg-white px-1 py-0.5 text-[10px] text-muted-foreground lg:inline">Ctrl+K</kbd>
              </button>
              <NotificationBell />
              <div className="text-right">
                <p className="text-sm font-semibold leading-tight text-gray-800">
                  {user?.first_name} {user?.last_name}
                </p>
                <p className="text-xs leading-tight text-muted-foreground">Administration</p>
              </div>
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-orange text-sm font-bold text-white shadow-orange">
                {initials}
              </div>
            </div>
          </header>

          <main className="flex-1 p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </RoleGuard>
  );
}
