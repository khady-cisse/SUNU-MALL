"""
Services d'administration technique SUNU MALL (apps/ops).

Concentrent la logique transversale du centre de contrôle technique :
- feature flags / mode maintenance (lu en base, jamais en dur) ;
- contrôles de santé (health checks) pour le monitoring d'infrastructure ;
- journal des alertes métier du centre de contrôle (alert center).

Tous les contrôles réseau dégradent proprement : une dépendance
injoignable (Redis, stockage) ne fait JAMAIS échouer une requête métier —
elle est signalée comme "degraded"/"down" au monitoring.
"""
import contextlib
import time

from django.conf import settings
from django.db import connection

from .models import Incident, SystemSetting


# --- Réglages de plateforme / feature flags ---

def get_setting(key, default=None):
    """Retourne la valeur typée d'un réglage, `default` si absent. Ne lève jamais."""
    with contextlib.suppress(SystemSetting.DoesNotExist):
        setting = SystemSetting.objects.filter(key=key).first()
        if setting is not None:
            return setting.typed_value()
    return default


def set_setting(key, raw, *, updated_by=None, label="", value_type="json", is_flag=False):
    """Écrit un réglage (créé à la volée). `value_type` pilote le cast."""
    setting, _ = SystemSetting.objects.get_or_create(
        key=key,
        defaults={"label": label or key, "value_type": value_type, "is_flag": is_flag},
    )
    setting.set_value(raw, updated_by=updated_by)
    return setting


def feature_flag(key, default=False):
    """Feature flag booléen. Désactivé si le réglage n'existe pas."""
    value = get_setting(key, default)
    return bool(value)


def maintenance_mode():
    """Vrai si la plateforme est en maintenance (commande technique admin)."""
    return feature_flag("site.maintenance_mode")


def maintenance_message():
    return get_setting("site.maintenance_message", "Sunu Mall est momentanément fermé pour maintenance.")


# --- Contrôles de santé ---

def _latency_ms(started):
    return round((time.monotonic() - started) * 1000, 1)


def _check_database():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return True


def _check_redis():
    import redis
    client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
    return client.ping()


def _check_storage():
    from django.core.files.storage import default_storage
    # HEAD (via Bucket.load()) sur le bucket : confirme que le stockage d'objets
    # répond. Un bucket inexistant provoque une erreur boto3 — on la remonte.
    default_storage.bucket.load()
    return True


def run_health_checks():
    """Batterie de contrôles de santé. Chaque contrôle rapporte son statut :
    "ok" / "degraded" (fonctionnel avec avertissement) / "down" (indisponible).
    Aucun contrôle ne lève : une exception = "down" pour la dépendance.
    """
    checks = [
        ("database", _check_database),
        ("redis", _check_redis),
        ("storage", _check_storage),
    ]
    results = []
    for name, fn in checks:
        started = time.monotonic()
        try:
            fn()
            status, detail = "ok", ""
        except Exception as exc:  # noqa: BLE001 — le check doit rendre compte, pas lever
            status, detail = "down", f"{type(exc).__name__}: {exc}"
        results.append({
            "name": name,
            "status": status,
            "latency_ms": _latency_ms(started),
            "detail": detail,
        })
    return results


def health_overall(checks=None):
    """Vue agrégée : "ok" si tout est vert, "degraded" si une dépendance
    secondaire est tombée, "down" si la base (critique) ne répond plus."""
    checks = checks or run_health_checks()
    by_status = {c["name"]: c["status"] for c in checks}
    if by_status.get("database") == "down":
        return "down"
    if "down" in by_status.values():
        return "degraded"
    return "ok"


# --- Centre d'alertes (spec : alert center admin) ---

def alert_center():
    """Journal agrége des alertes métier pour l'écran « Centre d'alertes ».

    Chaque alerte contient un code stable (pour le frontend), une sévérité,
    un compte et une cible. Les modules dont les modèles ne sont pas encore
    installés (plaintes) sont simplement ignorés.
    """
    from django.apps import apps
    from django.utils import timezone as tz
    from datetime import timedelta

    alerts = []

    # 1. Dossiers KYC en attente de vérification.
    if apps.is_installed("apps.kyc"):
        from apps.kyc.models import DriverKYC, SellerKYC
        pending_sellers = SellerKYC.objects.filter(status=SellerKYC.Status.PENDING).count()
        pending_drivers = DriverKYC.objects.filter(status=DriverKYC.Status.PENDING).count()
        if pending_sellers or pending_drivers:
            alerts.append({
                "code": "kyc_pending",
                "severity": "warning",
                "title": "Dossiers KYC en attente de vérification",
                "count": pending_sellers + pending_drivers,
                "subtitle": f"{pending_sellers} vendeur(s), {pending_drivers} livreur(s)",
                "target": "/admin-kyc",
            })

    # 2. Plaintes critiques non résolues.
    if apps.is_installed("apps.complaints"):
        from apps.complaints.models import Complaint
        open_critical = Complaint.objects.filter(
            priority=Complaint.Priority.CRITICAL,
            status__in=Complaint.OPEN_STATUSES,
        ).count()
        if open_critical:
            alerts.append({
                "code": "complaints_critical",
                "severity": "critical",
                "title": "Plaintes critiques non résolues",
                "count": open_critical,
                "target": "/admin-complaints",
            })

    # 3. Paiements échoués (7 derniers jours).
    if apps.is_installed("apps.payments"):
        from apps.payments.models import Payment
        failed = Payment.objects.filter(
            status=Payment.Status.FAILED,
            created_at__gte=tz.now() - timedelta(days=7),
        ).count()
        if failed:
            alerts.append({
                "code": "payments_failed",
                "severity": "critical",
                "title": "Paiements échoués (7 derniers jours)",
                "count": failed,
                "target": "/admin-payments",
            })

    # 4. Commandes annulées récemment (7 derniers jours).
    if apps.is_installed("apps.orders"):
        from apps.orders.models import Order
        cancelled = Order.objects.filter(
            status=Order.Status.CANCELLED,
            updated_at__gte=tz.now() - timedelta(days=7),
        ).count()
        if cancelled:
            alerts.append({
                "code": "orders_cancelled",
                "severity": "info",
                "title": "Commandes annulées (7 derniers jours)",
                "count": cancelled,
                "target": "/admin-orders",
            })

    # 5. Abonnements qui expirent sous 7 jours.
    if apps.is_installed("apps.monetization"):
        from apps.monetization.models import Subscription
        expiring = Subscription.objects.filter(
            status=Subscription.Status.ACTIVE,
            ends_at__gte=tz.now(),
            ends_at__lte=tz.now() + timedelta(days=7),
        ).count()
        if expiring:
            alerts.append({
                "code": "subscriptions_expiring",
                "severity": "warning",
                "title": "Abonnements qui expirent sous 7 jours",
                "count": expiring,
                "target": "/admin-subscriptions",
            })

    # 6. Vendeurs suspendus / bloqués.
    if apps.is_installed("apps.kyc"):
        from apps.kyc.models import SellerKYC
        suspended = SellerKYC.objects.filter(
            status__in=[SellerKYC.Status.SUSPENDED, SellerKYC.Status.BLOCKED]
        ).count()
        if suspended:
            alerts.append({
                "code": "sellers_suspended",
                "severity": "warning",
                "title": "Vendeurs suspendus ou bloqués",
                "count": suspended,
                "target": "/admin-sellers",
            })

    # 7. Incidents techniques ouverts.
    open_incidents = Incident.objects.exclude(status__in=[Incident.Status.RESOLVED, Incident.Status.CLOSED]).count()
    if open_incidents:
        alerts.append({
            "code": "incidents_open",
            "severity": "critical",
            "title": "Incidents techniques ouverts",
            "count": open_incidents,
            "target": "/admin-ops",
        })

    # 8. Accès d'urgence actifs (break-the-glass).
    from .models import EmergencyAccess
    active_emergency = EmergencyAccess.objects.filter(status=EmergencyAccess.Status.ACTIVE).count()
    if active_emergency:
        alerts.append({
            "code": "emergency_access_active",
            "severity": "warning",
            "title": "Accès d'urgence actifs (break-the-glass)",
            "count": active_emergency,
            "target": "/admin-ops",
        })

    return alerts