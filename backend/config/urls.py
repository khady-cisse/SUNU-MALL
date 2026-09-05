"""
Routes principales de l'API SUNU MALL.
Chaque app expose ses propres routes dans son fichier urls.py —
on les inclut ici sous un préfixe clair.
"""
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.auth.urls")),
    path("api/users/", include("apps.users.urls")),
    path("api/catalog/", include("apps.catalog.urls")),
    path("api/orders/", include("apps.orders.urls")),
    path("api/payments/", include("apps.payments.urls")),
    path("api/shopping/", include("apps.shopping.urls")),
    path("api/monetization/", include("apps.monetization.urls")),
    path("api/analytics/", include("apps.analytics.urls")),
    path("api/ia/", include("apps.ia.urls")),
    path("api/kyc/", include("apps.kyc.urls")),
    # Swagger/OpenAPI Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
