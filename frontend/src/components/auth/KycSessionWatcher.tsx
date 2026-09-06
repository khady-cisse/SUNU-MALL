import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { useMerchantKycStore } from "@/store/merchantKycStore";

/**
 * Règle de session des commerçants :
 * - Tant que l'identité (SellerKYC) n'est pas VERIFIED, le vendeur ne peut
 *   exister que DANS son espace (/merchant*, écran « en attente »).
 * - Dès qu'il sort de cet espace (bouton retour, flèche du navigateur,
 *   saisie d'une autre URL…), on le déconnecte immédiatement.
 * - Les pages d'authentification sont exemptées : on ne déconnecte jamais
 *   quelqu'un pendant qu'il se connecte.
 * Une fois approuvé (VERIFIED), aucune restriction : plein accès.
 */
const AUTH_ROUTES = /^\/(login|register-client|register-merchant|driver-login|verify-email)(\/|$)/;

export function KycSessionWatcher() {
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const merchantKyc = useMerchantKycStore();

  const isMerchant = !!user?.roles.includes("merchant");

  useEffect(() => {
    if (isMerchant) {
      merchantKyc.checkOnce();
    } else {
      merchantKyc.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, isMerchant]);

  useEffect(() => {
    const pending =
      isMerchant && merchantKyc.checked && merchantKyc.status !== "VERIFIED";
    const onMerchantSpace = location.pathname.startsWith("/merchant");
    const onAuthRoute = AUTH_ROUTES.test(location.pathname);
    if (pending && !onMerchantSpace && !onAuthRoute) {
      logout();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, user?.id, merchantKyc.checked, merchantKyc.status]);

  return <Outlet />;
}