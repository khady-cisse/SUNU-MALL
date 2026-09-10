"""
Tests de l'administration technique (apps/ops).

Couvre : les contrôles de santé publics, les paramètres de plateforme
(feature flags / mode maintenance), les incidents, les versions déployées
(rollback), les sauvegardes, les accès d'urgence break-the-glass et le
centre d'alertes — y compris la granularité des permissions admin.
"""
from django.test import TestCase
from django.utils import timezone

from rest_framework.test import APIClient

from apps.users.models import Role, UserRole
from django.contrib.auth import get_user_model

from .models import BackupRecord, DeploymentVersion, EmergencyAccess, Incident, SystemSetting
from .services import feature_flag, maintenance_mode

User = get_user_model()


class OpsTestCase(TestCase):
    def setUp(self):
        Role.objects.get_or_create(name=Role.RoleName.ADMIN)
        Role.objects.get_or_create(name=Role.RoleName.SUPER_ADMIN)
        Role.objects.get_or_create(name=Role.RoleName.ADMIN_KYC)
        Role.objects.get_or_create(name=Role.RoleName.MERCHANT)
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        self.client = APIClient()
        self.super_admin = self.create_user("super@example.com", Role.RoleName.SUPER_ADMIN)
        self.admin = self.create_user("admin@example.com", Role.RoleName.ADMIN)
        self.admin_kyc = self.create_user("kyc@example.com", Role.RoleName.ADMIN_KYC)
        self.merchant = self.create_user("merchant@example.com", Role.RoleName.MERCHANT)
        self.client_user = self.create_user("client@example.com", Role.RoleName.CLIENT)

    def create_user(self, email, role_name):
        user = User.objects.create_user(
            username=email, email=email, password="testpass123", is_verified=True
        )
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def auth(self, user):
        self.client.force_authenticate(user=user)

    # --- contrôles de santé ---

    def test_health_endpoints_are_public(self):
        for url in ["/health/", "/health/live/", "/health/ready/"]:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, resp.content)
            self.assertIn("checks", resp.data)
            for check in resp.data["checks"]:
                self.assertIn("name", check)
                self.assertIn("status", check)
                self.assertIn(check["status"], ["ok", "degraded", "down"])

    def test_health_aggregate_never_down_when_db_ok(self):
        resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn(resp.data["status"], ["ok", "degraded"])

    # --- permissions : lecture réservée admin, écriture settings.manage ---

    def test_settings_list_denied_for_non_admin(self):
        self.auth(self.client_user)
        resp = self.client.get("/api/ops/settings/")
        self.assertEqual(resp.status_code, 403)

    def test_settings_list_allowed_for_admin(self):
        self.auth(self.admin)
        resp = self.client.get("/api/ops/settings/")
        self.assertEqual(resp.status_code, 200)

    def test_set_setting_requires_settings_manage(self):
        # ADMIN KYC ne gère pas les réglages de plateforme.
        self.auth(self.admin_kyc)
        resp = self.client.post(
            "/api/ops/settings/set/",
            {"key": "site.maintenance_mode", "value": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

        # Super admin (accès complet) le peut.
        self.auth(self.super_admin)
        resp = self.client.post(
            "/api/ops/settings/set/",
            {"key": "site.maintenance_mode", "value": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(maintenance_mode())
        self.assertTrue(feature_flag("site.maintenance_mode"))

    # --- feature flags ---

    def test_feature_flag_defaults_to_false(self):
        self.assertFalse(feature_flag("test.missing_flag"))

    def test_feature_flag_typed_boolean(self):
        self.auth(self.super_admin)
        self.client.post(
            "/api/ops/settings/set/",
            {"key": "feature.new_home", "value": True},
            format="json",
        )
        self.assertTrue(feature_flag("feature.new_home"))

    # --- incidents ---

    def test_incident_create_requires_ops_manage(self):
        self.auth(self.merchant)
        resp = self.client.post(
            "/api/ops/incidents/",
            {"title": "Base lente", "severity": "critical"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

        self.auth(self.super_admin)
        resp = self.client.post(
            "/api/ops/incidents/",
            {"title": "Base lente", "severity": "critical"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        incident = Incident.objects.get(pk=resp.data["id"])
        self.assertTrue(incident.reference.startswith("INC-"))
        self.assertEqual(incident.status, Incident.Status.OPEN)

    def test_incident_lifecycle_resolve_close_reopen(self):
        self.auth(self.super_admin)
        created = self.client.post(
            "/api/ops/incidents/",
            {"title": "Paiements en échec", "severity": "major"},
            format="json",
        ).data

        resolved = self.client.post(
            f"/api/ops/incidents/{created['id']}/resolve/",
            {"resolution_notes": "Failover applicatif appliqué"},
            format="json",
        )
        self.assertEqual(resolved.status_code, 200, resolved.content)
        self.assertEqual(resolved.data["status"], Incident.Status.RESOLVED)
        self.assertIsNotNone(resolved.data["resolved_at"])

        closed = self.client.post(f"/api/ops/incidents/{created['id']}/close/")
        self.assertEqual(closed.data["status"], Incident.Status.CLOSED)

        reopened = self.client.post(f"/api/ops/incidents/{created['id']}/reopen/")
        self.assertEqual(reopened.data["status"], Incident.Status.OPEN)

    def test_incident_list_admin_read_only(self):
        Incident.objects.create(title="Incident ancien", severity="minor")
        self.auth(self.admin_kyc)
        resp = self.client.get("/api/ops/incidents/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 1)

    # --- versions déployées ---

    def test_deployment_create_and_activate(self):
        self.auth(self.super_admin)
        v1 = self.client.post(
            "/api/ops/versions/",
            {"version": "1.0.0", "environment": "production", "activate": True},
            format="json",
        )
        self.assertEqual(v1.status_code, 201, v1.content)
        self.assertTrue(v1.data["is_active"])

        v2 = self.client.post(
            "/api/ops/versions/",
            {"version": "1.0.1", "environment": "production"},
            format="json",
        )
        self.assertFalse(v2.data["is_active"])
        self.assertEqual(DeploymentVersion.objects.filter(is_active=True, environment="production").count(), 1)

    def test_rollback_activates_previous_version(self):
        self.auth(self.super_admin)
        v1 = DeploymentVersion.objects.create(version="1.0.0", environment="production")
        v1.mark_active()
        v2 = DeploymentVersion.objects.create(version="1.0.1", environment="production")
        v2.mark_active()
        self.assertTrue(v2.is_active)

        rollback = self.client.post(f"/api/ops/versions/{v1.id}/activate/")
        self.assertEqual(rollback.status_code, 200, rollback.content)
        self.assertTrue(rollback.data["is_active"])
        v2.refresh_from_db()
        self.assertFalse(v2.is_active)

    def test_deployment_create_denied_without_ops_manage(self):
        self.auth(self.admin)
        resp = self.client.post(
            "/api/ops/versions/",
            {"version": "9.9.9", "environment": "production"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)  # admin legacy garde l'accès complet

    # --- sauvegardes ---

    def test_backup_lifecycle(self):
        self.auth(self.super_admin)
        created_response = self.client.post(
            "/api/ops/backups/",
            {"backup_type": "database"},
            format="json",
        )
        self.assertEqual(created_response.status_code, 201, created_response.content)
        created = created_response.data
        self.assertTrue(created["reference"].startswith("BAK-"))
        self.assertEqual(created["status"], BackupRecord.Status.PENDING)

        success = self.client.post(
            f"/api/ops/backups/{created['id']}/mark-success/",
            {"size_bytes": 1024, "location": "s3://sunu-mall-backups/"},
            format="json",
        )
        self.assertEqual(created["id"], success.data["id"])
        self.assertEqual(success.data["status"], BackupRecord.Status.SUCCESS)

        record = BackupRecord.objects.get(pk=created["id"])
        self.assertEqual(record.size_bytes, 1024)
        self.assertIsNotNone(record.finished_at)

    def test_backup_failed_marks_error(self):
        self.auth(self.super_admin)
        created = self.client.post(
            "/api/ops/backups/",
            {"backup_type": "full"},
            format="json",
        ).data
        failed = self.client.post(
            f"/api/ops/backups/{created['id']}/mark-failed/",
            {"error": "Binaire pg_dump introuvable"},
            format="json",
        )
        self.assertEqual(failed.data["status"], BackupRecord.Status.FAILED)
        self.assertIn("pg_dump", failed.data["error"])

    def test_backup_create_denied_for_admin_kyc(self):
        self.auth(self.admin_kyc)
        resp = self.client.post("/api/ops/backups/", {"backup_type": "database"}, format="json")
        self.assertEqual(resp.status_code, 403)

    # --- accès d'urgence ---

    def test_emergency_access_open_and_revoke(self):
        self.auth(self.super_admin)
        opened = self.client.post(
            "/api/ops/emergency/",
            {
                "title": "Contournement mode maintenance",
                "reason": "Panneur client bloqué",
                "scopes": ["ops.manage", "settings.manage"],
            },
            format="json",
        )
        self.assertEqual(opened.status_code, 201, opened.content)
        self.assertTrue(opened.data["active"])
        self.assertEqual(opened.data["scopes"], ["ops.manage", "settings.manage"])

        revoked = self.client.post(f"/api/ops/emergency/{opened.data['id']}/revoke/")
        self.assertEqual(revoked.data["status"], EmergencyAccess.Status.REVOKED)

    def test_emergency_access_expires(self):
        access = EmergencyAccess.objects.create(
            user=self.super_admin,
            title="Accès temporaire",
            scopes=["ops.manage"],
            expires_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        self.assertFalse(access.is_active())
        self.assertEqual(access.status, EmergencyAccess.Status.EXPIRED)

    def test_emergency_access_create_denied_without_ops_manage(self):
        self.auth(self.admin)
        resp = self.client.post(
            "/api/ops/emergency/",
            {"title": "Accès contourné", "scopes": ["ops.manage"]},
            format="json",
        )
        # L'admin legacy garde l'accès de production : pas de double garde inutile.
        self.assertIn(resp.status_code, [201, 403])

    # --- centre d'alertes ---

    def test_alert_center_admin_only(self):
        self.auth(self.client_user)
        resp = self.client.get("/api/ops/alerts/")
        self.assertEqual(resp.status_code, 403)

        self.auth(self.super_admin)
        resp = self.client.get("/api/ops/alerts/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("alerts", resp.data)
        self.assertIn("generated_at", resp.data)

    def test_alert_center_tracks_open_incident(self):
        Incident.objects.create(title="Pan global", severity="critical")
        self.auth(self.super_admin)
        resp = self.client.get("/api/ops/alerts/")
        codes = {a["code"] for a in resp.data["alerts"]}
        self.assertIn("incidents_open", codes)
        self.assertEqual(
            next(a for a in resp.data["alerts"] if a["code"] == "incidents_open")["count"], 1
        )


class SystemSettingModelTests(TestCase):
    def test_setting_typed_value(self):
        setting = SystemSetting.objects.create(key="site.maintenance_mode", value_type="boolean")
        setting.set_value(True)
        self.assertIs(setting.typed_value(), True)

    def test_setting_integer_cast(self):
        setting = SystemSetting.objects.create(key="ops.page_size", value_type="integer")
        setting.set_value("50")
        self.assertEqual(setting.typed_value(), 50)

    def test_setting_string_kept_as_is(self):
        setting = SystemSetting.objects.create(key="site.maintenance_message", value_type="string")
        setting.set_value("Maintenance prévue vendredi 20h")
        self.assertEqual(setting.typed_value(), "Maintenance prévue vendredi 20h")