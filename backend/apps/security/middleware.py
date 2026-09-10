"""
Middleware de sécurité transversaux :
- RequestID : identifiant unique par requête (corrélation dans les journaux) ;
- MaintenanceMode : fenêtre de maintenance plateforme (voir apps/ops).
"""
import uuid

from django.http import JsonResponse


class RequestIDMiddleware:
    """Attribue un identifiant de requête `REQ-<uuid>` (header X-Request-ID
    fourni par le client s'il existe, sinon généré) exposé en réponse et
    dans les journaux de sécurité / d'audit."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or f"REQ-{uuid.uuid4().hex[:12]}"
        request.request_id = request_id
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response


class MaintenanceModeMiddleware:
    """Bloque les requêtes quand la plateforme est en mode maintenance.

    Le mode maintenance est activé par un admin via le centre de contrôle
    (réglage `site.maintenance_mode`, apps/ops). Les chemins de santé
    (/health*) restent accessibles ; un administrateur authentifié peut
    toujours passer pour diagnostiquer. Répond 503 JSON — aucune page HTML."""
    HEALTH_PREFIXES = ("/health", "/static", "/admin")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith(self.HEALTH_PREFIXES):
            return self.get_response(request)

        from apps.ops.services import maintenance_message, maintenance_mode
        if maintenance_mode():
            user = getattr(request, "user", None)
            if not (user and user.is_authenticated and user.is_admin()):
                return JsonResponse(
                    {
                        "error": "service_unavailable",
                        "message": maintenance_message(),
                    },
                    status=503,
                )
        return self.get_response(request)