from rest_framework.routers import DefaultRouter
from .views import SellerKYCViewSet, DriverKYCViewSet

router = DefaultRouter()
router.register(r"seller-kyc", SellerKYCViewSet, basename="seller-kyc")
router.register(r"driver-kyc", DriverKYCViewSet, basename="driver-kyc")

urlpatterns = router.urls