"""
Routes principales de l'API SUNU MALL.
Chaque app expose ses propres routes dans son fichier urls.py —
on les inclut ici sous un préfixe clair.
"""
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from apps.ops.views import HealthView

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
    path("api/commissions/", include("apps.commissions.urls")),
    path("api/ops/", include("apps.ops.urls")),
    path("api/complaints/", include("apps.complaints.urls")),
    path("api/security/", include("apps.security.urls")),
    path("api/search/", include("apps.search.urls")),
    path("api/reports/", include("apps.reports.urls")),
    # Contrôles de santé (publics) — voir apps.ops.views.HealthView
    path("health/live/", HealthView.as_view(mode="live"), name="health-live"),
    path("health/ready/", HealthView.as_view(mode="ready"), name="health-ready"),
    path("health/", HealthView.as_view(), name="health"),
    # Swagger/OpenAPI Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
