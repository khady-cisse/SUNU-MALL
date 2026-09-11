import { type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { LogOut } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { NotificationBell } from "@/components/layout/NotificationBell";
import { useAuthStore } from "@/store/authStore";
import { cn } from "@/lib/utils";

export interface DashboardNavItem {
  to: string;
  label: string;
  icon: ReactNode;
}

export function DashboardShell({ nav, title }: { nav: DashboardNavItem[]; title: string }) {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { pathname } = useLocation();
  const activeLabel = nav.find((item) => item.to === pathname)?.label ?? title;
  const initials = `${user?.first_name?.[0] ?? ""}${user?.last_name?.[0] ?? ""}`.toUpperCase() || "?";

  return (
    <div className="min-h-screen bg-muted">
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col overflow-hidden navy-panel p-5 md:flex">
        <Logo to={nav[0]?.to ?? "/"} light className="mb-8" />
        <p className="mb-4 text-xs uppercase tracking-wide text-white/50">{title}</p>
        <nav className="flex flex-1 flex-col gap-1 overflow-y-auto">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-white/80 transition-colors hover:bg-white/10",
                  isActive && "bg-white/15 text-white",
                )
              }
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={logout}
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-white/70 transition-colors hover:bg-white/10"
        >
          <LogOut className="h-4 w-4" />
          Déconnexion
        </button>
      </aside>
      <div className="flex flex-col md:pl-64">
        <header className="flex items-center justify-between border-b border-border bg-white px-6 py-4 md:hidden">
          <Logo to={nav[0]?.to ?? "/"} />
          <div className="flex items-center gap-1">
            <NotificationBell />
            <button onClick={logout} className="text-sm text-muted-foreground">
              Déconnexion
            </button>
          </div>
        </header>
        <header className="hidden items-center justify-between gap-4 border-b border-border bg-white px-6 py-4 md:flex">
          <h1 className="font-display text-lg font-bold text-gray-800">{activeLabel}</h1>
          <div className="flex items-center gap-3">
            <NotificationBell />
            <div className="text-right">
              <p className="text-sm font-semibold leading-tight text-gray-800">
                {user?.first_name} {user?.last_name}
              </p>
              <p className="text-xs leading-tight text-muted-foreground">{title}</p>
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
  );
}
