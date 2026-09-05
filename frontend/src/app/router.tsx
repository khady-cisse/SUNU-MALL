import { createBrowserRouter, Navigate } from "react-router-dom";

import { AuthLayout } from "@/components/layout/AuthLayout";
import { MarketplaceLayout } from "@/components/layout/MarketplaceLayout";
import { CheckoutLayout } from "@/components/layout/CheckoutLayout";
import { MerchantLayout } from "@/components/layout/MerchantLayout";
import { DriverLayout } from "@/components/layout/DriverLayout";
import { AdminLayout } from "@/components/layout/AdminLayout";

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
import AnalyticsPage from "@/pages/analytics";
import LiveSalesPage from "@/pages/live-sales";
import OrderDetailPage from "@/pages/order-detail";

import DriverDashboardPage from "@/pages/driver-dashboard";
import DriverDeliveryPage from "@/pages/driver-delivery";
import DriverProfilePage from "@/pages/driver-profile";

import AdminDashboardPage from "@/pages/admin";
import AdminUsersPage from "@/pages/admin-users";
import AdminManagersPage from "@/pages/admin-managers";
import AdminShopsPage from "@/pages/admin-shops";
import AdminOrdersPage from "@/pages/admin-orders";
import AdminPaymentsPage from "@/pages/admin-payments";
import AdminKycSellersPage from "@/pages/admin-kyc-sellers";
import AdminKycDriversPage from "@/pages/admin-kyc-drivers";

export const router = createBrowserRouter([
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
      { path: "/analytics", element: <AnalyticsPage /> },
      { path: "/live-sales", element: <LiveSalesPage /> },
      { path: "/order-detail", element: <OrderDetailPage /> },
      { path: "/merchant-notifications", element: <NotificationsPage /> },
    ],
  },

  {
    element: <DriverLayout />,
    children: [
      { path: "/driver-dashboard", element: <DriverDashboardPage /> },
      { path: "/driver-delivery", element: <DriverDeliveryPage /> },
      { path: "/driver-profile", element: <DriverProfilePage /> },
      { path: "/driver-notifications", element: <NotificationsPage /> },
    ],
  },

  {
    element: <AdminLayout />,
    children: [
      { path: "/admin", element: <AdminDashboardPage /> },
      { path: "/admin-users", element: <AdminUsersPage /> },
      { path: "/admin-managers", element: <AdminManagersPage /> },
      { path: "/admin-shops", element: <AdminShopsPage /> },
      { path: "/admin-orders", element: <AdminOrdersPage /> },
      { path: "/admin-payments", element: <AdminPaymentsPage /> },
      { path: "/admin-kyc-sellers", element: <AdminKycSellersPage /> },
      { path: "/admin-kyc-drivers", element: <AdminKycDriversPage /> },
      { path: "/admin-order-detail", element: <OrderDetailPage /> },
      { path: "/admin-notifications", element: <NotificationsPage /> },
    ],
  },

  { path: "*", element: <Navigate to="/home" replace /> },
]);
