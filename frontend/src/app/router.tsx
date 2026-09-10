import { createBrowserRouter, Navigate } from "react-router-dom";

import { AuthLayout } from "@/components/layout/AuthLayout";
import { MarketplaceLayout } from "@/components/layout/MarketplaceLayout";
import { CheckoutLayout } from "@/components/layout/CheckoutLayout";
import { MerchantLayout } from "@/components/layout/MerchantLayout";
import { DriverLayout } from "@/components/layout/DriverLayout";
import { PartnerLayout } from "@/components/layout/PartnerLayout";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { KycSessionWatcher } from "@/components/auth/KycSessionWatcher";

import SplashPage from "@/pages/splash";
import LoginPage from "@/pages/login";
import RegisterClientPage from "@/pages/register-client";
import RegisterMerchantPage from "@/pages/register-merchant";
import VerifyEmailPage from "@/pages/verify-email";
import DriverLoginPage from "@/pages/driver-login";

import HomePage from "@/pages/home";
import SearchPage from "@/pages/search";
import BoutiquesPage from "@/pages/boutiques";
import BoutiqueDetailPage from "@/pages/boutique-detail";
import ProductDetailPage from "@/pages/product-detail";
import CategoryIndexPage from "@/pages/category";
import CategoryDetailPage from "@/pages/category-detail";
import WishlistPage from "@/pages/wishlist";
import RecentlyViewedPage from "@/pages/recently-viewed";
import NotificationsPage from "@/pages/notifications";
import ContactPage from "@/pages/contact";
import MentionsLegalesPage from "@/pages/legal/mentions-legales";
import PolitiqueConfidentialitePage from "@/pages/legal/politique-confidentialite";
import ConditionsUtilisationPage from "@/pages/legal/conditions-utilisation";

import CartPage from "@/pages/cart";
import CheckoutAddressPage from "@/pages/checkout-address";
import CheckoutDeliveryPage from "@/pages/checkout-delivery";
import CheckoutPaymentPage from "@/pages/checkout-payment";
import OrderConfirmedPage from "@/pages/order-confirmed";
import OrdersPage from "@/pages/orders";
import TrackingPage from "@/pages/tracking";
import DeliveryConfirmPage from "@/pages/delivery-confirm";

import MerchantDashboardPage from "@/pages/merchant";
import CreateShopPage from "@/pages/create-shop";
import StoreSettingsPage from "@/pages/store-settings";
import AddProductPage from "@/pages/add-product";
import CatalogPage from "@/pages/catalog";
import SubscriptionsPage from "@/pages/subscriptions";
import OffersPage from "@/pages/offers";
import PromotionsPage from "@/pages/promotions";
import MerchantSupportPage from "@/pages/support";
import AnalyticsPage from "@/pages/analytics";
import LiveSalesPage from "@/pages/live-sales";
import OrderDetailPage from "@/pages/order-detail";
import SellerWalletPage from "@/pages/seller-wallet";
import SellerPayoutsPage from "@/pages/seller-payouts";

import DriverDashboardPage from "@/pages/driver-dashboard";
import DriverDeliveryPage from "@/pages/driver-delivery";
import DriverProfilePage from "@/pages/driver-profile";
import DriverPasswordChangePage from "@/pages/driver-password-change";

import PartnerDashboardPage from "@/pages/partner";
import PartnerDeliveriesPage from "@/pages/partner-deliveries";
import PartnerDeliveryPage from "@/pages/partner-delivery";
import PartnerDriversPage from "@/pages/partner-drivers";
import PartnerZonesPage from "@/pages/partner-zones";
import PartnerFinancesPage from "@/pages/partner-finances";
import PartnerProfilePage from "@/pages/partner-profile";

import AdminDashboardPage from "@/pages/admin";
import AdminUsersPage from "@/pages/admin-users";
import AdminUserDetailPage from "@/pages/admin-user-detail";
import AdminManagersPage from "@/pages/admin-managers";
import AdminShopsPage from "@/pages/admin-shops";
import AdminSellersPage from "@/pages/admin-sellers";
import AdminSellerDetailPage from "@/pages/admin-seller-detail";
import AdminProductsPage from "@/pages/admin-products";
import AdminCategoriesPage from "@/pages/admin-categories";
import AdminOrdersPage from "@/pages/admin-orders";
import AdminPaymentsPage from "@/pages/admin-payments";
import AdminSubscriptionsPage from "@/pages/admin-subscriptions";
import AdminRefundsPage from "@/pages/admin-refunds";
import AdminKycSellersPage from "@/pages/admin-kyc-sellers";
import AdminKycDriversPage from "@/pages/admin-kyc-drivers";
import AdminDriversPage from "@/pages/admin-drivers";
import AdminDeliveriesPage from "@/pages/admin-deliveries";
import AdminPartnersPage from "@/pages/admin-partners";
import AdminFinancePage from "@/pages/admin-finance";
import AdminComplaintsPage from "@/pages/admin-complaints";
import AdminComplaintDetailPage from "@/pages/admin-complaint-detail";
import AdminSupportPage from "@/pages/admin-support";
import AdminNotificationsPage from "@/pages/notifications";
import AdminSearchPage from "@/pages/admin-search";
import AdminSecurityPage from "@/pages/admin-security";
import AdminAnalyticsPage from "@/pages/admin-analytics";
import AdminReportsPage from "@/pages/admin-reports";
import AdminMonitoringPage from "@/pages/admin-monitoring";
import AdminIncidentsPage from "@/pages/admin-incidents";
import AdminIncidentDetailPage from "@/pages/admin-incident-detail";
import AdminLogsPage from "@/pages/admin-logs";
import AdminDeploymentsPage from "@/pages/admin-deployments";
import AdminFeatureFlagsPage from "@/pages/admin-feature-flags";
import AdminMaintenancePage from "@/pages/admin-maintenance";
import AdminBackupsPage from "@/pages/admin-backups";
import AdminEmergencyPage from "@/pages/admin-emergency";

export const router = createBrowserRouter([
  {
    element: <KycSessionWatcher />,
    children: [
      { path: "/", element: <Navigate to="/home" replace /> },

  {
    element: <AuthLayout />,
    children: [
      { path: "/splash", element: <SplashPage /> },
      { path: "/login", element: <LoginPage /> },
      { path: "/register-client", element: <RegisterClientPage /> },
      { path: "/register-merchant", element: <RegisterMerchantPage /> },
      { path: "/verify-email", element: <VerifyEmailPage /> },
      { path: "/driver-login", element: <DriverLoginPage /> },
    ],
  },

  {
    element: <MarketplaceLayout />,
    children: [
      { path: "/home", element: <HomePage /> },
      { path: "/search", element: <SearchPage /> },
      { path: "/boutiques", element: <BoutiquesPage /> },
      { path: "/boutiques/:slug", element: <BoutiqueDetailPage /> },
      { path: "/product/:id", element: <ProductDetailPage /> },
      { path: "/category", element: <CategoryIndexPage /> },
      { path: "/category/:slug", element: <CategoryDetailPage /> },
      { path: "/wishlist", element: <WishlistPage /> },
      { path: "/recently-viewed", element: <RecentlyViewedPage /> },
      { path: "/notifications", element: <NotificationsPage /> },
      { path: "/contact", element: <ContactPage /> },
      { path: "/mentions-legales", element: <MentionsLegalesPage /> },
      { path: "/politique-de-confidentialite", element: <PolitiqueConfidentialitePage /> },
      { path: "/conditions-utilisation", element: <ConditionsUtilisationPage /> },
    ],
  },

  {
    element: <CheckoutLayout />,
    children: [
      { path: "/cart", element: <CartPage /> },
      { path: "/checkout-address", element: <CheckoutAddressPage /> },
      { path: "/checkout-delivery", element: <CheckoutDeliveryPage /> },
      { path: "/checkout-payment", element: <CheckoutPaymentPage /> },
      { path: "/order-confirmed", element: <OrderConfirmedPage /> },
      { path: "/orders", element: <OrdersPage /> },
      { path: "/tracking", element: <TrackingPage /> },
      { path: "/delivery-confirm", element: <DeliveryConfirmPage /> },
    ],
  },

  {
    element: <MerchantLayout />,
    children: [
      { path: "/merchant", element: <MerchantDashboardPage /> },
      { path: "/create-shop", element: <CreateShopPage /> },
      { path: "/store-settings", element: <StoreSettingsPage /> },
      { path: "/add-product", element: <AddProductPage /> },
      { path: "/catalog", element: <CatalogPage /> },
      { path: "/subscriptions", element: <SubscriptionsPage /> },
      { path: "/offers", element: <OffersPage /> },
      { path: "/promotions", element: <PromotionsPage /> },
      { path: "/support", element: <MerchantSupportPage /> },
      { path: "/analytics", element: <AnalyticsPage /> },
      { path: "/live-sales", element: <LiveSalesPage /> },
      { path: "/order-detail", element: <OrderDetailPage /> },
      { path: "/merchant-wallet", element: <SellerWalletPage /> },
      { path: "/merchant-payouts", element: <SellerPayoutsPage /> },
      { path: "/merchant-notifications", element: <NotificationsPage /> },
    ],
  },

  {
    element: <DriverLayout />,
    children: [
      { path: "/driver-dashboard", element: <DriverDashboardPage /> },
      { path: "/driver-delivery", element: <DriverDeliveryPage /> },
      { path: "/driver-profile", element: <DriverProfilePage /> },
      { path: "/driver-password-change", element: <DriverPasswordChangePage /> },
      { path: "/driver-notifications", element: <NotificationsPage /> },
    ],
  },

  {
    element: <PartnerLayout />,
    children: [
      { path: "/partner", element: <PartnerDashboardPage /> },
      { path: "/partner-deliveries", element: <PartnerDeliveriesPage /> },
      { path: "/partner-delivery", element: <PartnerDeliveryPage /> },
      { path: "/partner-drivers", element: <PartnerDriversPage /> },
      { path: "/partner-zones", element: <PartnerZonesPage /> },
      { path: "/partner-finances", element: <PartnerFinancesPage /> },
      { path: "/partner-profile", element: <PartnerProfilePage /> },
      { path: "/partner-notifications", element: <NotificationsPage /> },
    ],
  },

  {
    element: <AdminLayout />,
    children: [
      { path: "/admin", element: <AdminDashboardPage /> },
      { path: "/admin-search", element: <AdminSearchPage /> },
      { path: "/admin-users", element: <AdminUsersPage /> },
      { path: "/admin-users/:id", element: <AdminUserDetailPage /> },
      { path: "/admin-sellers", element: <AdminSellersPage /> },
      { path: "/admin-sellers/:id", element: <AdminSellerDetailPage /> },
      { path: "/admin-shops", element: <AdminShopsPage /> },
      { path: "/admin-products", element: <AdminProductsPage /> },
      { path: "/admin-categories", element: <AdminCategoriesPage /> },
      { path: "/admin-orders", element: <AdminOrdersPage /> },
      { path: "/admin-order-detail", element: <OrderDetailPage /> },
      { path: "/admin-payments", element: <AdminPaymentsPage /> },
      { path: "/admin-subscriptions", element: <AdminSubscriptionsPage /> },
      { path: "/admin-refunds", element: <AdminRefundsPage /> },
      { path: "/admin-kyc-sellers", element: <AdminKycSellersPage /> },
      { path: "/admin-kyc-drivers", element: <AdminKycDriversPage /> },
      { path: "/admin-drivers", element: <AdminDriversPage /> },
      { path: "/admin-deliveries", element: <AdminDeliveriesPage /> },
      { path: "/admin-partners", element: <AdminPartnersPage /> },
      { path: "/admin-finance", element: <AdminFinancePage /> },
      { path: "/admin-complaints", element: <AdminComplaintsPage /> },
      { path: "/admin-complaints/:id", element: <AdminComplaintDetailPage /> },
      { path: "/admin-support", element: <AdminSupportPage /> },
      { path: "/admin-notifications", element: <AdminNotificationsPage /> },
      { path: "/admin-managers", element: <AdminManagersPage /> },
      { path: "/admin-security", element: <AdminSecurityPage /> },
      { path: "/admin-analytics", element: <AdminAnalyticsPage /> },
      { path: "/admin-reports", element: <AdminReportsPage /> },
      { path: "/admin-monitoring", element: <AdminMonitoringPage /> },
      { path: "/admin-incidents", element: <AdminIncidentsPage /> },
      { path: "/admin-incidents/:id", element: <AdminIncidentDetailPage /> },
      { path: "/admin-logs", element: <AdminLogsPage /> },
      { path: "/admin-deployments", element: <AdminDeploymentsPage /> },
      { path: "/admin-feature-flags", element: <AdminFeatureFlagsPage /> },
      { path: "/admin-maintenance", element: <AdminMaintenancePage /> },
      { path: "/admin-backups", element: <AdminBackupsPage /> },
      { path: "/admin-emergency", element: <AdminEmergencyPage /> },
    ],
  },

  { path: "*", element: <Navigate to="/home" replace /> },
    ],
  },
]);
