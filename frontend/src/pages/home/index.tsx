import { Link } from "react-router-dom";
import {
  ArrowRight,
  Bike,
  ChevronRight,
  Headphones,
  Shield,
  ShoppingBag,
  Store,
  Tag,
  Truck,
  Zap,
} from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as catalogApi from "@/api/catalog";
import * as iaApi from "@/api/ia";
import { ProductCard } from "@/components/marketplace/ProductCard";
import { ProductRail } from "@/components/marketplace/ProductRail";
import { CategoryCarousel } from "@/components/marketplace/CategoryCarousel";
import { HeroSlideshow } from "@/components/marketplace/HeroSlideshow";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { useRecentlyViewedStore } from "@/store/recentlyViewedStore";
import { useAuthStore } from "@/store/authStore";
import type { Product } from "@/types";

const WHY_ITEMS = [
  { icon: Truck, title: "Livraison rapide", desc: "Méthode rapide au Sénégal" },
  { icon: Shield, title: "Paiement sécurisé", desc: "100% sécurisé" },
  { icon: Tag, title: "Meilleurs prix", desc: "Promotions chaque jour" },
  { icon: Headphones, title: "Support 24/7", desc: "Assistance dédiée" },
  { icon: Zap, title: "Satisfait ou remboursé", desc: "Politique de retour" },
];

const SPACES = [
  { icon: ShoppingBag, title: "Client", desc: "Panier multi-boutiques, paiement Wave/OM/CB, suivi GPS.", path: "/home", bg: "bg-orange/10", ic: "text-orange" },
  { icon: Store, title: "Commerçant", desc: "Gestion catalogue, livreurs affiliés, analytics.", path: "/register-merchant", bg: "bg-blue-50", ic: "text-blue-600" },
  { icon: Bike, title: "Livreur", desc: "Courses assignées, itinéraire, preuve de livraison.", path: "/driver-login", bg: "bg-green-50", ic: "text-green-600" },
];

export default function HomePage() {
  const {
    data: products,
    loading: loadingProducts,
    error: productsError,
    refetch: refetchProducts,
  } = useAsync(() => catalogApi.listProducts(), []);
  const { data: categories, loading: loadingCategories } = useAsync(() => catalogApi.listCategories(), []);
  const { data: sponsoredProducts, loading: loadingSponsored } = useAsync(() => catalogApi.listSponsoredProducts(), []);
  const { data: bestSellers, loading: loadingBestSellers } = useAsync(() => catalogApi.listBestSellers(), []);

  const user = useAuthStore((s) => s.user);
  const { data: recommendations, loading: loadingRecommendations } = useAsync(
    () => (user ? iaApi.getPersonalizedRecommendations() : Promise.resolve([])),
    [user?.id],
  );

  const topCategories = (categories ?? []).filter((c) => !c.parent);
  const topCategoryIds = topCategories.map((c) => c.id).join(",");
  const { data: categoryProductsMap, loading: loadingCategoryProducts } = useAsync(async () => {
    const entries = await Promise.all(
      topCategories.map(async (c) => [c.id, await catalogApi.listProducts({ category: c.id })] as const),
    );
    return Object.fromEntries(entries) as Record<string, Product[]>;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topCategoryIds]);

  const recentlyViewedIds = useRecentlyViewedStore((s) => s.productIds);
  const { data: recentlyViewed } = useAsync(async () => {
    const settled = await Promise.allSettled(recentlyViewedIds.map((id) => catalogApi.getProduct(id)));
    return settled
      .filter((r): r is PromiseFulfilledResult<Product> => r.status === "fulfilled")
      .map((r) => r.value);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recentlyViewedIds.join(",")]);

  return (
    <div className="bg-gray-50">
      {/* ─── HERO ─── */}
      <section
        style={{ background: "linear-gradient(135deg, #FFF8F0 0%, #FFF3E8 40%, #FDEEDD 100%)" }}
        className="border-b border-orange/10"
      >
        <div className="mx-auto grid max-w-7xl items-center gap-10 px-4 py-10 md:grid-cols-[1fr_1fr] md:py-14">
          <div>
            <h1 className="font-display text-4xl font-extrabold leading-tight text-gray-900 md:text-5xl">
              Tout le Sénégal
              <br />
              <span className="text-orange">dans une seule</span>
              <br />
              plateforme
            </h1>
            <p className="mt-4 max-w-md text-base leading-relaxed text-gray-500">
              Achetez en toute confiance parmi des milliers de boutiques et faites-vous livrer partout.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/search" className="btn-orange inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-bold">
                Découvrir les boutiques
              </Link>
              <Link
                to="/register-merchant"
                className="inline-flex items-center gap-2 rounded-xl bg-navy px-6 py-3 text-sm font-bold text-white transition-colors hover:bg-navy-2"
              >
                Créer ma boutique
              </Link>
            </div>

            <div className="mt-8 flex flex-wrap gap-6">
              {[
                { icon: Truck, title: "Livraison rapide", sub: "partout au Sénégal" },
                { icon: Shield, title: "Paiement sécurisé", sub: "Wave, Orange Money, CB" },
                { icon: Headphones, title: "Support 24/7", sub: "Nous sommes là" },
              ].map(({ icon: Icon, title, sub }) => (
                <div key={title} className="flex items-center gap-2">
                  <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-white shadow-sm">
                    <Icon className="h-4 w-4 text-orange" />
                  </div>
                  <div>
                    <p className="text-xs font-bold text-gray-700">{title}</p>
                    <p className="text-[11px] text-gray-400">{sub}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="relative flex min-h-[340px] items-end justify-center overflow-hidden rounded-[2rem] sm:min-h-[420px]">
            <HeroSlideshow
              images={[
                { src: "/hero-shopper.jpg", alt: "Cliente Sunu Mall avec ses achats" },
                { src: "/live-shopping.jpg", alt: "Vente en direct sur Sunu Mall" },
                { src: "/merchant-store.jpg", alt: "Commerçant conseillant une cliente" },
                { src: "/order-handoff.jpg", alt: "Remise de commande Sunu Mall" },
              ]}
            />
            <div className="absolute inset-0 bg-gradient-to-t from-white via-white/60 to-white/5" />
            <img
              src="/hero-illustration.png"
              alt="Sunu Mall marketplace illustration"
              className="relative z-10 w-full max-w-[420px] drop-shadow-2xl"
            />
          </div>
        </div>
      </section>

      {/* ─── CATÉGORIES POPULAIRES ─── */}
      <section className="mx-auto max-w-7xl px-4 py-10">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="font-display text-xl font-bold text-gray-800">Catégories populaires</h2>
          <Link to="/category" className="flex items-center gap-1 text-sm font-semibold text-orange transition-all hover:gap-2">
            Voir toutes <ChevronRight className="h-4 w-4" />
          </Link>
        </div>
        {loadingCategories ? (
          <div className="flex gap-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="aspect-[4/3] w-52 shrink-0 rounded-2xl" />
            ))}
          </div>
        ) : (
          <CategoryCarousel categories={categories ?? []} />
        )}
      </section>

      {/* ─── SPONSORISÉ ─── */}
      <ProductRail
        title="Sponsorisé"
        viewAllHref="/search?sponsored=true"
        products={sponsoredProducts}
        loading={loadingSponsored}
        sponsored
      />

      {/* ─── MEILLEURES VENTES ─── */}
      <ProductRail title="Meilleures ventes" viewAllHref="/search" products={bestSellers} loading={loadingBestSellers} />

      {/* ─── RECOMMANDÉ POUR VOUS (connecté uniquement) ─── */}
      {user && (
        <ProductRail title="Recommandé pour vous" products={recommendations} loading={loadingRecommendations} />
      )}

      {/* ─── NOUVEAUTÉS ─── */}
      <section className="mx-auto max-w-7xl px-4 py-6">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="font-display text-xl font-bold text-gray-800">Nouveautés</h2>
          <Link to="/search" className="flex items-center gap-1 text-sm font-semibold text-orange transition-all hover:gap-2">
            Voir tout <ChevronRight className="h-4 w-4" />
          </Link>
        </div>
        {loadingProducts ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="aspect-square w-full" />
            ))}
          </div>
        ) : productsError ? (
          <ErrorState onRetry={refetchProducts} />
        ) : products?.length === 0 ? (
          <EmptyState title="Aucun produit pour le moment" description="Revenez bientôt, de nouvelles boutiques arrivent chaque jour." />
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {products?.slice(0, 6).map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        )}
      </section>

      {/* ─── PAR CATÉGORIE ─── */}
      {topCategories.map((c) => (
        <ProductRail
          key={c.id}
          title={c.name}
          viewAllHref={`/category/${c.id}`}
          products={categoryProductsMap?.[c.id]}
          loading={loadingCategoryProducts}
        />
      ))}

      {/* ─── RÉCEMMENT CONSULTÉS ─── */}
      <ProductRail title="Récemment consultés" viewAllHref="/recently-viewed" products={recentlyViewed} />

      {/* ─── POURQUOI SUNU MALL ─── */}
      <section className="border-y border-gray-100 bg-white py-10">
        <div className="mx-auto max-w-7xl px-4">
          <h2 className="mb-6 text-center font-display text-xl font-bold text-gray-800">Pourquoi choisir Sunu Mall ?</h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-5">
            {WHY_ITEMS.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="flex flex-col items-center gap-2 p-4 text-center">
                <div className="grid h-12 w-12 place-items-center rounded-xl bg-orange/10">
                  <Icon className="h-6 w-6 text-orange" />
                </div>
                <p className="text-sm font-semibold text-gray-700">{title}</p>
                <p className="text-xs text-gray-400">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── ESPACES UTILISATEURS ─── */}
      <section className="mx-auto max-w-7xl px-4 py-10">
        <div className="mb-8 text-center">
          <span className="text-xs font-bold uppercase tracking-widest text-orange">Pour tout le monde</span>
          <h2 className="mt-2 font-display text-2xl font-bold text-gray-800">Un espace pour chacun</h2>
        </div>
        <div className="mx-auto grid max-w-5xl gap-4 md:grid-cols-3">
          {SPACES.map((r) => (
            <Link
              key={r.title}
              to={r.path}
              className="group rounded-xl border border-gray-100 bg-white p-5 transition-all hover:border-orange/30 hover:shadow-md"
            >
              <div className={`h-12 w-12 rounded-xl ${r.bg} ${r.ic} grid place-items-center`}>
                <r.icon className="h-6 w-6" />
              </div>
              <h3 className="mt-4 font-display font-bold text-gray-800">{r.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-gray-400">{r.desc}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-xs font-bold text-orange transition-all group-hover:gap-2">
                Voir l'espace <ArrowRight className="h-3.5 w-3.5" />
              </span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
