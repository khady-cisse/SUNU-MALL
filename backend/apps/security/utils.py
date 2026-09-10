"""
Journal de sécurité : enregistrement d'événements depuis le reste du projet.
"""
from django.conf import settings
from django.utils import timezone

from .models import AdminAuditLog, SecurityLog


def _client_ip(request):
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _client_user_agent(request):
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")


def _safe_log(fn):
    """Décore une écriture de journal pour qu'elle ne lève JAMAIS."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 — le journal ne doit jamais casser le métier
            return None
    return wrapper


@_safe_log
def _write_security_log(user, action, ip_address, user_agent, metadata):
    if settings.DISABLE_SECURITY_LOGS:
        return None
    return SecurityLog.objects.create(
        user=user if user and user.is_authenticated else None,
        action=action,
        ip_address=ip_address,
        user_agent=user_agent[:500],
        metadata=metadata or {},
    )


def log_security_event(
    user,
    action,
    request=None,
    metadata=None,
    *,
    ip_address=None,
    user_agent=None,
):
    """Trace une action sensible. Ne lève JAMAIS : la sécurité ne doit pas
    faire échouer l'action métier qui a déclenché le journal."""
    return _write_security_log(
        user,
        action,
        ip_address=ip_address or _client_ip(request),
        user_agent=user_agent or _client_user_agent(request),
        metadata=metadata or {},
    )


@_safe_log
def _write_admin_audit_log(admin, action, object_type, object_id, summary,
                           changes, ip_address, user_agent, metadata):
    return AdminAuditLog.objects.create(
        admin=admin if admin and admin.is_authenticated else None,
        action=action,
        object_type=object_type,
        object_id=object_id,
        summary=summary,
        changes=changes or {},
        ip_address=ip_address,
        user_agent=user_agent[:500],
        metadata=metadata or {},
    )


def log_admin_event(
    admin,
    action,
    request=None,
    *,
    object_type="",
    object_id="",
    summary="",
    changes=None,
    metadata=None,
    ip_address=None,
    user_agent=None,
):
    """Trace une action réalisée depuis le centre de contrôle (admin)."""
    return _write_admin_audit_log(
        admin,
        action,
        object_type,
        object_id,
        summary,
        changes or {},
        ip_address or _client_ip(request),
        user_agent or _client_user_agent(request),
        metadata or {},
    )


def prune_security_logs(retention_days=None):
    """Purge des journaux plus anciens que la durée de rétention (politique de
    conservation, spec §17). Appelé par Celery Beat, idempotent."""
    from datetime import timedelta

    retention_days = retention_days or settings.SECURITY_LOG_RETENTION_DAYS
    cutoff = timezone.now() - timedelta(days=retention_days)
    deleted, _ = SecurityLog.objects.filter(created_at__lt=cutoff).delete()
    return deleted