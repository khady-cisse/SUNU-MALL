"""
Tests des rapports administrateur (apps/reports).

Le stockage par défaut est remplacé par un stockage local temporaire pour
que la suite s'exécute sans MinIO. Couvre : la permission admin, les erreurs
(type/format inconnus) et la génération CSV/PDF (URL + nom de fichier).
"""
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from rest_framework.test import APIClient

from apps.users.models import Role, UserRole

User = get_user_model()

_TMP_STORAGE = {"location": tempfile.mkdtemp(prefix="sunu-reports-")}


@override_settings(STORAGES={
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": _TMP_STORAGE,
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
})
class ReportsTestCase(TestCase):
    def setUp(self):
        Role.objects.get_or_create(name=Role.RoleName.ADMIN)
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        self.client = APIClient()
        self.admin = self.create_user("admin@example.com", Role.RoleName.ADMIN)
        self.customer = self.create_user("client@example.com", Role.RoleName.CLIENT)

    def create_user(self, email, role_name):
        user = User.objects.create_user(
            username=email, email=email, password="testpass123", is_verified=True
        )
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def test_reports_require_admin(self):
        self.client.force_authenticate(user=self.customer)
        resp = self.client.get("/api/reports/global/?fmt=csv")
        self.assertEqual(resp.status_code, 403)

    def test_unknown_report_type_returns_404(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/reports/inexistant/?fmt=csv")
        self.assertEqual(resp.status_code, 404)

    def test_invalid_format_returns_400(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/reports/global/?fmt=xlsx")
        self.assertEqual(resp.status_code, 400)

    def test_global_csv_report(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/reports/global/?fmt=csv")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["url"].endswith(".csv"))
        self.assertTrue(resp.data["filename"].endswith(".csv"))
        self.assertGreater(resp.data["size"], 0)

    def test_finance_pdf_report(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/reports/finance/?fmt=pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["url"].endswith(".pdf"))
        self.assertTrue(resp.data["filename"].endswith(".pdf"))
        self.assertGreater(resp.data["size"], 0)
