"""
Tests unitaires pour le RBAC de l'application users.
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.users.models import User, Role, Permission, UserRole, RolePermission


class RBACModelTests(TestCase):
    """Tests pour les modèles RBAC."""

    def setUp(self):
        self.client = APIClient()
        # Créer les rôles et permissions via le signal (simulé ou direct)
        self.admin_role, _ = Role.objects.get_or_create(name=Role.RoleName.ADMIN)
        self.merchant_role, _ = Role.objects.get_or_create(name=Role.RoleName.MERCHANT)
        self.client_role, _ = Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        self.driver_role, _ = Role.objects.get_or_create(name=Role.RoleName.DRIVER)

        # Créer une permission de test
        self.perm_view_product, _ = Permission.objects.get_or_create(
            code='special_view_product',
            defaults={'label': 'Voir les produits spéciaux'}
        )

        # Créer des utilisateurs de test
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='testpass123',
            first_name='Admin',
            last_name='User'
        )
        UserRole.objects.create(user=self.admin_user, role=self.admin_role)

        self.merchant_user = User.objects.create_user(
            username='merchant',
            email='merchant@example.com',
            password='testpass123',
            first_name='Merchant',
            last_name='User'
        )
        UserRole.objects.create(user=self.merchant_user, role=self.merchant_role)

        self.client_user = User.objects.create_user(
            username='client',
            email='client@example.com',
            password='testpass123',
            first_name='Client',
            last_name='User'
        )
        UserRole.objects.create(user=self.client_user, role=self.client_role)

        self.driver_user = User.objects.create_user(
            username='driver',
            email='driver@example.com',
            password='testpass123',
            first_name='Driver',
            last_name='User'
        )
        UserRole.objects.create(user=self.driver_user, role=self.driver_role)

    def test_user_has_role(self):
        """Vérifie que la méthode has_role fonctionne."""
        self.assertTrue(self.admin_user.has_role(Role.RoleName.ADMIN))
        self.assertFalse(self.admin_user.has_role(Role.RoleName.MERCHANT))
        self.assertTrue(self.merchant_user.has_role(Role.RoleName.MERCHANT))
        self.assertTrue(self.client_user.has_role(Role.RoleName.CLIENT))
        self.assertTrue(self.driver_user.has_role(Role.RoleName.DRIVER))

    def test_admin_has_all_permissions(self):
        """Vérifie que l'admin a toutes les permissions."""
        self.assertTrue(self.admin_user.has_permission('view_product'))
        self.assertTrue(self.admin_user.has_permission('create_product'))
        self.assertTrue(self.admin_user.has_permission('any_permission_that_doesnt_exist'))  # Admin a tout

    def test_user_has_permission(self):
        """Vérifie que la méthode has_permission fonctionne."""
        # Assigner une permission au rôle merchant
        RolePermission.objects.get_or_create(role=self.merchant_role, permission=self.perm_view_product)
        
        self.assertTrue(self.merchant_user.has_permission('special_view_product'))
        self.assertFalse(self.client_user.has_permission('special_view_product'))

    def test_get_permissions(self):
        """Vérifie que la méthode get_permissions fonctionne."""
        RolePermission.objects.get_or_create(role=self.merchant_role, permission=self.perm_view_product)
        
        merchant_perms = self.merchant_user.get_permissions()
        self.assertIn(self.perm_view_product, merchant_perms)
        
        admin_perms = self.admin_user.get_permissions()
        self.assertGreater(len(admin_perms), 0)


class RBACAPITests(TestCase):
    """Tests pour les API RBAC."""

    def setUp(self):
        self.client = APIClient()
        # Créer les rôles
        self.admin_role, _ = Role.objects.get_or_create(name=Role.RoleName.ADMIN)
        self.merchant_role, _ = Role.objects.get_or_create(name=Role.RoleName.MERCHANT)
        self.client_role, _ = Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        self.driver_role, _ = Role.objects.get_or_create(name=Role.RoleName.DRIVER)

        self.user_list_url = reverse('user-list')

        # Créer des utilisateurs
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='testpass123',
            is_verified=True
        )
        UserRole.objects.create(user=self.admin_user, role=self.admin_role)

        self.merchant_user = User.objects.create_user(
            username='merchant',
            email='merchant@example.com',
            password='testpass123',
            is_verified=True
        )
        UserRole.objects.create(user=self.merchant_user, role=self.merchant_role)

        self.client_user = User.objects.create_user(
            username='client',
            email='client@example.com',
            password='testpass123',
            is_verified=True
        )
        UserRole.objects.create(user=self.client_user, role=self.client_role)

        self.driver_user = User.objects.create_user(
            username='driver',
            email='driver@example.com',
            password='testpass123',
            is_verified=True
        )
        UserRole.objects.create(user=self.driver_user, role=self.driver_role)

    def assert_admin_only_actions_forbidden(self, user):
        self.client.force_authenticate(user=user)
        response = self.client.patch(
            reverse('user-detail', args=[self.client_user.id]),
            {'first_name': 'Blocked'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_access_protected_endpoints_and_admin_actions(self):
        """Vérifie que l'admin accède aux endpoints protégés et aux actions réservées."""
        self.client.force_authenticate(user=self.admin_user)

        list_response = self.client.get(self.user_list_url)
        update_response = self.client.patch(
            reverse('user-detail', args=[self.merchant_user.id]),
            {'first_name': 'Updated by admin'},
            format='json',
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)

    def test_merchant_access_to_protected_endpoints(self):
        """Vérifie les accès du rôle merchant aux endpoints protégés."""
        self.client.force_authenticate(user=self.merchant_user)

        # La liste des utilisateurs est réservée à l'admin (anti-énumération :
        # un commerçant ne doit pas pouvoir lister emails/téléphones des autres).
        self.assertEqual(self.client.get(self.user_list_url).status_code, status.HTTP_403_FORBIDDEN)
        self.assert_admin_only_actions_forbidden(self.merchant_user)

    def test_client_access_to_protected_endpoints(self):
        """Vérifie les accès du rôle client aux endpoints protégés."""
        self.client.force_authenticate(user=self.client_user)

        self.assertEqual(self.client.get(self.user_list_url).status_code, status.HTTP_403_FORBIDDEN)
        self.assert_admin_only_actions_forbidden(self.client_user)

    def test_driver_access_to_protected_endpoints(self):
        """Vérifie les accès du rôle driver aux endpoints protégés."""
        self.client.force_authenticate(user=self.driver_user)

        self.assertEqual(self.client.get(self.user_list_url).status_code, status.HTTP_403_FORBIDDEN)
        self.assert_admin_only_actions_forbidden(self.driver_user)

    def test_unauthenticated_user_cannot_access_protected_endpoints(self):
        """Vérifie qu'un utilisateur non authentifié ne peut pas accéder aux endpoints protégés."""
        self.client.force_authenticate(user=None)

        self.assertEqual(self.client.get(self.user_list_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            self.client.patch(
                reverse('user-detail', args=[self.admin_user.id]),
                {'first_name': 'Blocked'},
                format='json',
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_user_serializer_includes_roles_and_permissions(self):
        """Vérifie que le serializer User inclut les rôles et permissions."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(reverse('user-detail', args=[self.admin_user.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('roles', response.data)
        self.assertIn('permissions', response.data)
        self.assertIn('admin', response.data['roles'])


class CreateAdminCommandTests(TestCase):
    """Tests de la commande `manage.py create_admin`."""

    def setUp(self):
        from django.core.management import call_command
        self.call_command = call_command

    def test_creates_verified_admin_with_role(self):
        self.call_command(
            'create_admin',
            email='admin@sunumall.com',
            password='Admin@12345',
            username='admin@sunumall.com',
        )
        user = User.objects.get(email='admin@sunumall.com')
        self.assertTrue(user.is_verified)
        self.assertTrue(user.is_active)
        self.assertTrue(user.has_role(Role.RoleName.ADMIN))
        self.assertTrue(user.check_password('Admin@12345'))

    def test_is_idempotent_and_restores_verified(self):
        user = User.objects.create_user(
            username='admin@sunumall.com', email='admin@sunumall.com',
            password='oldpass123', is_verified=False,
        )
        self.call_command(
            'create_admin', email='admin@sunumall.com', password='newpass123',
        )
        user.refresh_from_db()
        self.assertTrue(user.is_verified)
        self.assertTrue(user.check_password('newpass123'))
        self.assertEqual(User.objects.filter(email='admin@sunumall.com').count(), 1)

    def test_super_admin_flag_grants_both_roles(self):
        self.call_command(
            'create_admin', email='admin@sunumall.com', password='Admin@12345', super_admin=True,
        )
        user = User.objects.get(email='admin@sunumall.com')
        self.assertTrue(user.has_role(Role.RoleName.ADMIN))
        self.assertTrue(user.has_role(Role.RoleName.SUPER_ADMIN))

    def test_specialized_role_grants_only_that_admin_role(self):
        self.call_command(
            'create_admin', email='admin.kyc@sunumall.com',
            password='Admin@12345', roles=['admin_kyc'],
        )
        user = User.objects.get(email='admin.kyc@sunumall.com')
        self.assertTrue(user.has_role(Role.RoleName.ADMIN_KYC))
        self.assertFalse(user.has_role(Role.RoleName.ADMIN))
        self.assertFalse(user.has_role(Role.RoleName.SUPER_ADMIN))

    def test_multiple_roles_and_super_admin_flag(self):
        self.call_command(
            'create_admin', email='admin.finance@sunumall.com',
            password='Admin@12345', roles=['admin_finance', 'admin_support'],
            super_admin=True,
        )
        user = User.objects.get(email='admin.finance@sunumall.com')
        self.assertTrue(user.has_role(Role.RoleName.ADMIN_FINANCE))
        self.assertTrue(user.has_role(Role.RoleName.ADMIN_SUPPORT))
        self.assertTrue(user.has_role(Role.RoleName.SUPER_ADMIN))
        self.assertFalse(user.has_role(Role.RoleName.ADMIN))

    def test_role_all_grants_every_admin_role(self):
        self.call_command('create_admin', email='admin.all@sunumall.com', roles=['all'])
        user = User.objects.get(email='admin.all@sunumall.com')
        for role in Role.ADMIN_ROLES:
            self.assertTrue(user.has_role(role), f"rôle {role} manquant")
