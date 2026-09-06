import { Link } from "react-router-dom";
import { Logo } from "@/components/brand/Logo";

const FOOTER_COLUMNS: [string, { label: string; to?: string }[]][] = [
  [
    "Plateforme",
    [
      { label: "Accueil", to: "/home" },
      { label: "Catégories", to: "/category" },
      { label: "Boutiques", to: "/boutiques" },
      { label: "Mes commandes", to: "/orders" },
    ],
  ],
  ["Support", [{ label: "FAQ", to: "/contact#faq" }, { label: "Contact", to: "/contact" }, { label: "Aide livreurs", to: "/driver-login" }]],
  [
    "Vendeurs",
    [{ label: "Créer boutique", to: "/register-merchant" }, { label: "Abonnements", to: "/subscriptions" }, { label: "Guide vendeur", to: "/contact#faq" }],
  ],
  ["Paiement", [{ label: "Wave", to: "/contact#faq" }, { label: "Orange Money", to: "/contact#faq" }, { label: "Carte bancaire", to: "/contact#faq" }]],
];

export function Footer() {
  return (
    <footer className="navy-panel">
      <div className="mx-auto max-w-7xl px-4 py-12">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-5">
          <div className="col-span-2 md:col-span-1">
            <Logo size={36} light />
            <p className="mt-3 text-xs leading-relaxed text-white/60">La marketplace qui connecte le Sénégal.</p>
          </div>
          {FOOTER_COLUMNS.map(([title, items]) => (
            <div key={title}>
              <p className="mb-3 font-display text-sm font-bold">{title}</p>
              <ul className="space-y-2">
                {items.map(({ label, to }) => (
                  <li key={label}>
                    {to ? (
                      <Link to={to} className="text-xs text-white/50 transition-colors hover:text-orange">
                        {label}
                      </Link>
                    ) : (
                      <span className="cursor-pointer text-xs text-white/50 transition-colors hover:text-orange">
                        {label}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-10 flex flex-col items-center justify-between gap-4 border-t border-white/10 pt-6 text-xs text-white/40 md:flex-row">
          <p>© 2026 SUNU MALL — NEJ digital</p>
          <div className="flex items-center gap-4">
            <Link to="/mentions-legales" className="transition-colors hover:text-white">
              Mentions légales
            </Link>
            <Link to="/politique-de-confidentialite" className="transition-colors hover:text-white">
              Politique de confidentialité
            </Link>
            <Link to="/conditions-utilisation" className="transition-colors hover:text-white">
              Conditions d'utilisation
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
