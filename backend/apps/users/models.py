"""
Modèles liés aux utilisateurs de SUNU MALL.
"""
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.utils import timezone


class User(AbstractUser):
    """
    Utilisateur de base. On étend le User Django plutôt que de le
    remplacer entièrement, pour garder la compatibilité avec
    l'admin Django et le système d'auth standard.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    # Comptes créés par un admin (livreurs) : le mot de passe initial est
    # provisoire, l'utilisateur doit le changer dès sa première connexion.
    must_change_password = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        ordering = ['-created_at']

    def check_password(self, raw_password):
        return super().check_password(raw_password)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def has_role(self, name):
        return self.user_roles.filter(role__name=name).exists()

    def has_permission(self, permission_code):
        """Vérifie si l'utilisateur a une permission spécifique."""
        # Admin a toutes les permissions
        if self.has_role(Role.RoleName.ADMIN):
            return True
        # Vérifie via les rôles
        return RolePermission.objects.filter(
            role__role_users__user=self,
            permission__code=permission_code
        ).exists()

    def get_permissions(self):
        """Récupère toutes les permissions de l'utilisateur."""
        if self.has_role(Role.RoleName.ADMIN):
            return Permission.objects.all()
        return Permission.objects.filter(
            permission_roles__role__role_users__user=self
        ).distinct()

    def __str__(self):
        return f"{self.email} ({self.get_full_name()})"


class Role(models.Model):
    class RoleName(models.TextChoices):
        ADMIN = 'admin', 'Administrateur'
        MERCHANT = 'merchant', 'Commerçant'
        CLIENT = 'client', 'Client'
        DRIVER = 'driver', 'Livreur'

    id = models.AutoField(primary_key=True)
    name = models.CharField(
        max_length=100,
        unique=True,
        choices=RoleName.choices
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.get_name_display()


class Permission(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=100, unique=True)
    label = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.label}"


class UserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_roles')
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='role_users')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'role']


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='role_permissions')
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name='permission_roles')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['role', 'permission']


class Session(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    refresh_token_hash = models.CharField(max_length=255)
    device_info = models.JSONField(default=dict)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def revoke(self):
        self.expires_at = timezone.now()
        self.save()

    def __str__(self):
        return f"Session for {self.user.email}"


class Token(models.Model):
    class TokenType(models.TextChoices):
        EMAIL_VERIFICATION = 'email_verification', 'Email Verification'
        PASSWORD_RESET = 'password_reset', 'Password Reset'

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tokens')
    token = models.CharField(max_length=255, unique=True)
    type = models.CharField(max_length=50, choices=TokenType.choices)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        return not self.used_at and timezone.now() <= self.expires_at

    def mark_used(self):
        self.used_at = timezone.now()
        self.save()

    def __str__(self):
        return f"{self.type} token for {self.user.email}"


@receiver(post_migrate)
def create_default_roles_and_permissions(sender, **kwargs):
    """Créer les rôles et permissions par défaut après les migrations."""
    from django.apps import apps
    Role = apps.get_model('users', 'Role')
    Permission = apps.get_model('users', 'Permission')
    RolePermission = apps.get_model('users', 'RolePermission')

    # 1. Créer les rôles par défaut
    roles = [
        (Role.RoleName.ADMIN, 'Administrateur avec tous les droits'),
        (Role.RoleName.MERCHANT, 'Commerçant gérant sa propre boutique'),
        (Role.RoleName.CLIENT, 'Client faisant des achats sur la plateforme'),
        (Role.RoleName.DRIVER, 'Livreur effectuant les livraisons'),
    ]

    role_objects = {}
    for role_name, role_description in roles:
        role, _ = Role.objects.get_or_create(
            name=role_name,
            defaults={'description': role_description}
        )
        role_objects[role_name] = role

    # 2. Définir toutes les permissions nécessaires
    permissions = [
        # Permissions Utilisateurs
        ('view_user', 'Voir les utilisateurs'),
        ('create_user', 'Créer un utilisateur'),
        ('edit_user', 'Modifier un utilisateur'),
        ('delete_user', 'Supprimer un utilisateur'),
        ('suspend_user', 'Suspendre un utilisateur'),
        
        # Permissions Boutiques
        ('view_store', 'Voir les boutiques'),
        ('create_store', 'Créer une boutique'),
        ('edit_store', 'Modifier une boutique'),
        ('delete_store', 'Supprimer une boutique'),
        ('validate_store', 'Valider une boutique'),
        ('suspend_store', 'Suspendre une boutique'),
        
        # Permissions Produits
        ('view_product', 'Voir les produits'),
        ('create_product', 'Créer un produit'),
        ('edit_product', 'Modifier un produit'),
        ('delete_product', 'Supprimer un produit'),
        ('manage_inventory', 'Gérer le stock'),
        
        # Permissions Commandes
        ('view_order', 'Voir les commandes'),
        ('create_order', 'Créer une commande'),
        ('edit_order', 'Modifier une commande'),
        ('update_order_status', 'Mettre à jour le statut d\'une commande'),
        ('assign_driver', 'Assigner un livreur à une commande'),
        
        # Permissions Livraisons
        ('view_delivery', 'Voir les livraisons'),
        ('accept_delivery', 'Accepter une livraison'),
        ('update_delivery_status', 'Mettre à jour le statut de livraison'),
        
        # Permissions Paiements
        ('view_payment', 'Voir les paiements'),
        ('manage_payment', 'Gérer les paiements'),
        ('process_refund', 'Traiter un remboursement'),
        
        # Permissions Monétisation
        ('view_commission', 'Voir les commissions'),
        ('manage_commission', 'Gérer les commissions'),
        ('manage_subscription', 'Gérer les abonnements'),
        ('manage_sponsored_products', 'Gérer les produits sponsorisés'),
        
        # Permissions Analytics
        ('view_analytics', 'Voir les analytics'),
        ('view_detailed_analytics', 'Voir les analytics détaillées'),
    ]

    permission_objects = {}
    for code, label in permissions:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={'label': label}
        )
        permission_objects[code] = perm

    # 3. Assigner les permissions aux rôles

    # --- ADMIN : Toutes les permissions ---
    admin_role = role_objects[Role.RoleName.ADMIN]
    for perm in permission_objects.values():
        RolePermission.objects.get_or_create(role=admin_role, permission=perm)

    # --- MERCHANT : Permissions liées à sa boutique ---
    merchant_role = role_objects[Role.RoleName.MERCHANT]
    merchant_perms = [
        'view_store', 'create_store', 'edit_store',
        'view_product', 'create_product', 'edit_product', 'delete_product', 'manage_inventory',
        'view_order', 'update_order_status', 'assign_driver',
        'view_payment',
        'view_analytics',
    ]
    for code in merchant_perms:
        RolePermission.objects.get_or_create(role=merchant_role, permission=permission_objects[code])

    # --- CLIENT : Permissions de base ---
    client_role = role_objects[Role.RoleName.CLIENT]
    client_perms = [
        'view_store', 'view_product',
        'create_order', 'view_order',
    ]
    for code in client_perms:
        RolePermission.objects.get_or_create(role=client_role, permission=permission_objects[code])

    # --- DRIVER : Permissions liées aux livraisons ---
    driver_role = role_objects[Role.RoleName.DRIVER]
    driver_perms = [
        'view_delivery', 'accept_delivery', 'update_delivery_status',
        'view_order',
    ]
    for code in driver_perms:
        RolePermission.objects.get_or_create(role=driver_role, permission=permission_objects[code])
