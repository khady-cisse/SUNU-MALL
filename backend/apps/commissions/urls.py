from rest_framework.routers import DefaultRouter

from .views import (
    CommissionTransactionViewSet,
    PayoutViewSet,
    SellerSubscriptionViewSet,
    SellerWalletViewSet,
)

router = DefaultRouter()
router.register("subscription", SellerSubscriptionViewSet, basename="commission-subscription")
router.register("wallet", SellerWalletViewSet, basename="seller-wallet")
router.register("commissions", CommissionTransactionViewSet, basename="commission-transaction")
router.register("payouts", PayoutViewSet, basename="payout")

urlpatterns = router.urls