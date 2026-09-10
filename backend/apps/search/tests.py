"""
Tests de la recherche globale et avancée (apps/search).

Couvre : l'isolation par rôle (admin requis), le seuil minimal de 2
caractères, la recherche textuelle multi-entités et les filtres de la
recherche avancée (entités ciblées + statut).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework.test import APIClient

from apps.users.models import Role, UserRole

User = get_user_model()


class SearchTestCase(TestCase):
    def setUp(self):
        Role.objects.get_or_create(name=Role.RoleName.ADMIN)
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        self.client = APIClient()
        self.admin = self.create_user("admin@example.com", Role.RoleName.ADMIN)
        self.customer = self.create_user("client@example.com", Role.RoleName.CLIENT)
        self.customer2 = self.create_user("autre@example.com", Role.RoleName.CLIENT)

    def create_user(self, email, role_name):
        user = User.objects.create_user(
            username=email, email=email, password="testpass123", is_verified=True
        )
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def test_global_search_requires_admin(self):
        self.client.force_authenticate(user=self.customer)
        resp = self.client.get("/api/search/?q=client")
        self.assertEqual(resp.status_code, 403)

    def test_global_search_rejects_short_query(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/search/?q=a")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {})

    def test_global_search_returns_users(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/search/?q=client")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("users", resp.data)
        self.assertEqual(resp.data["users"][0]["label"], self.customer.email)

    def test_advanced_search_requires_admin(self):
        self.client.force_authenticate(user=self.customer)
        resp = self.client.post("/api/search/advanced/", {"query": "client"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_advanced_search_targets_only_requested_entities(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/search/advanced/",
            {"query": "example", "entities": ["users"], "limit": 10},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("users", resp.data)
        self.assertNotIn("orders", resp.data)

    def test_advanced_search_status_filter(self):
        self.client.force_authenticate(user=self.admin)
        # "active" sur les utilisateurs = is_active=True, le compte l'est.
        resp = self.client.post(
            "/api/search/advanced/",
            {"query": "client", "entities": ["users"], "status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("users", resp.data)

    def test_advanced_search_all_entities_by_default(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/search/advanced/",
            {"query": "example", "limit": 5},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("users", resp.data)