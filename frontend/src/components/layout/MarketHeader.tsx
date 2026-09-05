import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronDown, Heart, LayoutDashboard, LogOut, Package, Search, ShoppingCart, User } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { CategoryMenu } from "@/components/marketplace/CategoryMenu";
import { NotificationBell } from "@/components/layout/NotificationBell";
import { useAuthStore } from "@/store/authStore";
import { roleHomePath } from "@/lib/roles";
import * as shoppingApi from "@/api/shopping";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { label: "Accueil", to: "/home" },
  { label: "Catégories", to: "/category" },
  { label: "Boutiques", to: "/boutiques" },
  { label: "Promotions", to: "/search" },
  { label: "Contact", to: "/contact" },
];

const ROLE_LABEL: Record<string, string> = {
  client: "Mes commandes",
  merchant: "Mon tableau de bord",
  driver: "Mes livraisons",
  admin: "Administration",
};

export function MarketHeader() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const [query, setQuery] = useState("");
  const [accountOpen, setAccountOpen] = useState(false);
  const [cartCount, setCartCount] = useState(0);
  const [favCount, setFavCount] = useState(0);

  useEffect(() => {
    if (!user) {
      setCartCount(0);
      setFavCount(0);
      return;
    }
    shoppingApi
      .getCart()
      .then((cart) => setCartCount(cart.items.reduce((sum, item) => sum + item.quantity, 0)))
      .catch(() => setCartCount(0));
    shoppingApi
      .getWishlist()
      .then((wishlist) => setFavCount(wishlist.items.length))
      .catch(() => setFavCount(0));
  }, [user]);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    navigate(query.trim() ? `/search?q=${encodeURIComponent(query.trim())}` : "/search");
  }

  function handleLogout() {
    logout();
    setAccountOpen(false);
    navigate("/home");
  }

  return (
    <header className="sticky top-0 z-50 border-b border-gray-100 bg-white shadow-sm">
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3">
        <Logo to="/home" size={48} className="shrink-0" />

        <form onSubmit={handleSearch} className="ml-2 flex max-w-4xl flex-1 items-center sm:ml-6">
          <div className="flex w-full rounded-lg border border-gray-200 shadow-sm transition-all focus-within:border-orange focus-within:ring-2 focus-within:ring-orange/20">
            <CategoryMenu />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Rechercher un produit, boutique…"
              className="flex-1 rounded-none bg-white px-4 py-2.5 text-sm text-gray-700 outline-none placeholder:text-gray-400"
            />
            <button
              type="submit"
              className="flex items-center gap-2 rounded-r-lg bg-orange px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-orange-dark"
            >
              <Search className="h-4 w-4" />
              <span className="hidden sm:block">Rechercher</span>
            </button>
          </div>
        </form>

        <div className="ml-auto flex shrink-0 items-center gap-2">
          <NotificationBell />

          {user?.roles.includes("client") && (
            <Link to="/orders" className="group relative flex flex-col items-center gap-0.5 px-2 py-1">
              <Package className="h-5 w-5 text-gray-500 transition-colors group-hover:text-orange" />
              <span className="hidden text-[10px] text-gray-400 sm:block">Commandes</span>
            </Link>
          )}

          <Link to="/wishlist" className="group relative flex flex-col items-center gap-0.5 px-2 py-1">
            <div className="relative">
              <Heart className={cn("h-5 w-5 transition-colors", favCount > 0 ? "fill-orange text-orange" : "text-gray-500 group-hover:text-orange")} />
              {favCount > 0 && (
                <span className="absolute -right-1.5 -top-1.5 grid h-4 w-4 place-items-center rounded-full bg-orange text-[10px] font-bold text-white">
                  {favCount}
                </span>
              )}
            </div>
            <span className="hidden text-[10px] text-gray-400 sm:block">Favoris</span>
          </Link>

          <Link to="/cart" className="group relative flex flex-col items-center gap-0.5 px-2 py-1">
            <div className="relative">
              <ShoppingCart className="h-5 w-5 text-gray-500 transition-colors group-hover:text-orange" />
              {cartCount > 0 && (
                <span className="absolute -right-1.5 -top-1.5 grid h-4 w-4 place-items-center rounded-full bg-orange text-[10px] font-bold text-white">
                  {cartCount}
                </span>
              )}
            </div>
            <span className="hidden text-[10px] text-gray-400 sm:block">Panier</span>
          </Link>

          {user ? (
            <div className="relative">
              <button
                onClick={() => setAccountOpen((v) => !v)}
                className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-2 transition-colors hover:bg-gray-50"
              >
                <span className="grid h-6 w-6 place-items-center rounded-full bg-navy text-[11px] font-bold text-white">
                  {user.first_name.charAt(0).toUpperCase() || user.email.charAt(0).toUpperCase()}
                </span>
                <span className="hidden max-w-[90px] truncate text-sm text-gray-700 sm:block">
                  {user.first_name || user.email}
                </span>
                <ChevronDown className="h-4 w-4 text-gray-400" />
              </button>
              {accountOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setAccountOpen(false)} />
                  <div className="absolute right-0 top-full z-20 mt-2 w-52 overflow-hidden rounded-xl border border-gray-100 bg-white shadow-lg">
                    <div className="border-b border-gray-100 px-4 py-3">
                      <p className="truncate text-sm font-semibold text-navy">
                        {user.first_name} {user.last_name}
                      </p>
                      <p className="truncate text-xs text-gray-400">{user.email}</p>
                    </div>
                    <Link
                      to={user.roles.includes("client") ? "/orders" : roleHomePath(user.roles)}
                      onClick={() => setAccountOpen(false)}
                      className="flex items-center gap-2 px-4 py-2.5 text-sm text-navy hover:bg-gray-50"
                    >
                      <LayoutDashboard className="h-4 w-4" /> {ROLE_LABEL[user.roles[0]] ?? "Mon espace"}
                    </Link>
                    <button
                      onClick={handleLogout}
                      className="flex w-full items-center gap-2 border-t border-gray-100 px-4 py-2.5 text-sm text-danger hover:bg-danger/5"
                    >
                      <LogOut className="h-4 w-4" /> Se déconnecter
                    </button>
                  </div>
                </>
              )}
            </div>
          ) : (
            <Link
              to="/login"
              className="group flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-2 transition-colors hover:bg-gray-50"
            >
              <User className="h-4 w-4 text-gray-500 group-hover:text-orange" />
              <span className="hidden text-sm text-gray-600 sm:block">Mon compte</span>
            </Link>
          )}
        </div>
      </div>

      <nav className="border-t border-gray-100 bg-white">
        <div className="mx-auto flex max-w-7xl items-center gap-1 overflow-x-auto px-4 scrollbar-hide">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.label}
              to={link.to}
              className="whitespace-nowrap border-b-2 border-transparent px-3 py-2.5 text-sm text-gray-600 transition-colors hover:border-orange/40 hover:text-orange"
            >
              {link.label}
            </Link>
          ))}
        </div>
      </nav>
    </header>
  );
}
