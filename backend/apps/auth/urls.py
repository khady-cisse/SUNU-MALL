from django.urls import path
from rest_framework_simplejwt.views import (
    TokenRefreshView,
    TokenVerifyView,
    TokenBlacklistView,
)
from .views import (
    RegisterView,
    LoginView,
    VerifyEmailView,
    ResendVerificationEmailView,
    VerifiedTokenObtainPairView,
    GuestCheckoutView,
    SetPasswordView,
    ChangePasswordView,
    RequestPhoneOTPView,
    VerifyPhoneOTPView,
    LogoutView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('login/', LoginView.as_view(), name='auth_login'),
    path('verify-email/', VerifyEmailView.as_view(), name='auth_verify_email'),
    path('resend-verification/', ResendVerificationEmailView.as_view(), name='auth_resend_verification'),
    path('guest-checkout/', GuestCheckoutView.as_view(), name='auth_guest_checkout'),
    path('set-password/', SetPasswordView.as_view(), name='auth_set_password'),
    path('change-password/', ChangePasswordView.as_view(), name='auth_change_password'),
    path('request-phone-otp/', RequestPhoneOTPView.as_view(), name='auth_request_phone_otp'),
    path('verify-phone-otp/', VerifyPhoneOTPView.as_view(), name='auth_verify_phone_otp'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
    path('token/', VerifiedTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('token/blacklist/', TokenBlacklistView.as_view(), name='token_blacklist'),
]
