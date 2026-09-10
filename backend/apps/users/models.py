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
    # Numéro de téléphone confirmé par code OTP (spec §14) : le compte peut
    # exister sans, mais certaines actions sensibles peuvent l'exiger.
    phone_verified = models.BooleanField(default=False)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
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

    def has_any_role(self, names):
        return self.user_roles.filter(role__name__in=list(names)).exists()

    def is_admin(self):
        """Vrai si l'utilisateur porte l'un des rôles d'administration.

        Couvre l'ancien rôle unique "admin" (accès complet, rétrocompatible)
        et les rôles spécialisés introduits avec le centre de contrôle
        (super_admin, admin_kyc, admin_support, admin_finance,
        admin_marketplace, admin_delivery). Le backend vérifie ensuite les
        permissions fines (HasPermission) là où la granularité compte.
        """
        return self.has_any_role(Role.ADMIN_ROLES)

    def is_super_admin(self):
        """Accès complet : super admin ou ancien rôle admin maître."""
        return self.has_any_role([Role.RoleName.ADMIN, Role.RoleName.SUPER_ADMIN])

    def is_partner(self):
        """Vrai si l'utilisateur est un partenaire logistique (role partner)."""
        return self.has_role(Role.RoleName.PARTNER)

    def has_permission(self, permission_code):
        """Vérifie si l'utilisateur a une permission spécifique."""
        # Super admin / ancien admin maître : toutes les permissions
        if self.is_super_admin():
            return True
        # Vérifie via les rôles
        return RolePermission.objects.filter(
            role__role_users__user=self,
            permission__code=permission_code
        ).exists()

    def get_permissions(self):
        """Récupère toutes les permissions de l'utilisateur."""
        if self.is_super_admin():
            return Permission.objects.all()
        return Permission.objects.filter(
            permission_roles__role__role_users__user=self
        ).distinct()

    def __str__(self):
        return f"{self.email} ({self.get_full_name()})"


class Role(models.Model):
    class RoleName(models.TextChoices):
        # --- Rôles d'administration (centre de contrôle, spec §42) ---
        ADMIN = 'admin', 'Administrateur'
        SUPER_ADMIN = 'super_admin', 'Super Administrateur'
        ADMIN_KYC = 'admin_kyc', 'Admin KYC'
        ADMIN_SUPPORT = 'admin_support', 'Admin Support'
        ADMIN_FINANCE = 'admin_finance', 'Admin Finance'
        ADMIN_MARKETPLACE = 'admin_marketplace', 'Admin Marketplace'
        ADMIN_DELIVERY = 'admin_delivery', 'Admin Livraison'
        # --- Utilisateurs classiques ---
        MERCHANT = 'merchant', 'Commerçant'
        CLIENT = 'client', 'Client'
        DRIVER = 'driver', 'Livreur'
        PARTNER = 'partner', 'Partenaire de livraison'

    # Tous les rôles considérés comme "administration" pour les vues admin.
    ADMIN_ROLES = [
        RoleName.ADMIN, RoleName.SUPER_ADMIN, RoleName.ADMIN_KYC, RoleName.ADMIN_SUPPORT,
        RoleName.ADMIN_FINANCE, RoleName.ADMIN_MARKETPLACE, RoleName.ADMIN_DELIVERY,
    ]

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


class PhoneOTP(models.Model):
    """Code OTP à 6 chiffres pour confirmer un numéro de téléphone.

    Le code n'est JAMAIS stocké en clair : seul son empreinte SHA-256 est
    conservée. Expiration courte et essais limités (réglages PHONE_OTP_*).
    """

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="phone_otps")
    phone = models.CharField(max_length=20)
    code_hash = models.CharField(max_length=64)
    attempts = models.IntegerField(default=0)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def generate_code(cls):
        import random

        return f"{random.randint(0, 999999):06d}"

    @staticmethod
    def _hash(code):
        import hashlib

        return hashlib.sha256(code.encode()).hexdigest()

    def valid_for_verification(self, max_attempts):
        if self.verified_at is not None:
            return False
        if self.attempts >= max_attempts:
            return False
        return self.expires_at > timezone.now()

    def verify(self, code, max_attempts):
        import secrets

        if not self.valid_for_verification(max_attempts):
            return False
        candidate = self._hash(code)
        if not secrets.compare_digest(candidate, self.code_hash):
            self.attempts += 1
            self.save(update_fields=["attempts"])
            return False
        self.verified_at = timezone.now()
        self.save(update_fields=["verified_at"])
        return True

    def __str__(self):
        return f"PhoneOTP pour {self.user.email} ({self.phone})"


@receiver(post_migrate)
def create_default_roles_and_permissions(sender, **kwargs):
    """Créer les rôles et permissions par défaut après les migrations."""
    from django.apps import apps
    Role = apps.get_model('users', 'Role')
    Permission = apps.get_model('users', 'Permission')
    RolePermission = apps.get_model('users', 'RolePermission')

    # 1. Créer les rôles par défaut
    roles = [
        (Role.RoleName.ADMIN, 'Administrateur avec tous les droits (rétrocompatible)'),
        (Role.RoleName.SUPER_ADMIN, 'Super Administrateur — accès complet'),
        (Role.RoleName.ADMIN_KYC, "Admin KYC — gestion des vérifications d'identité"),
        (Role.RoleName.ADMIN_SUPPORT, 'Admin Support — clients, commandes, tickets, plaintes'),
        (Role.RoleName.ADMIN_FINANCE, 'Admin Finance — paiements, abonnements, remboursements, rapports'),
        (Role.RoleName.ADMIN_MARKETPLACE, 'Admin Marketplace — vendeurs, boutiques, produits, commandes'),
        (Role.RoleName.ADMIN_DELIVERY, 'Admin Livraison — livreurs, livraisons, incidents'),
        (Role.RoleName.MERCHANT, 'Commerçant gérant sa propre boutique'),
        (Role.RoleName.CLIENT, 'Client faisant des achats sur la plateforme'),
        (Role.RoleName.DRIVER, 'Livreur effectuant les livraisons'),
        (Role.RoleName.PARTNER, 'Entreprise partenaire logistique (espace partenaire)'),
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
        ('assign_delivery', 'Affecter une livraison à un livreur'),
        ('view_driver', 'Voir les livreurs'),
        ('create_driver', 'Créer un livreur'),
        ('edit_driver', 'Modifier un livreur'),
        ('view_delivery_zone', 'Voir les zones de livraison'),
        
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

        # --- Permissions du centre de contrôle (spec §43) ---
        # Vendeurs
        ('sellers.view', 'Voir les vendeurs'),
        ('sellers.edit', 'Modifier un vendeur'),
        ('sellers.suspend', 'Suspendre un vendeur'),
        ('sellers.block', 'Bloquer un vendeur'),
        # Boutiques (admin)
        ('stores.manage', 'Gérer les boutiques (admin)'),
        # Produits (admin)
        ('products.manage', 'Gérer les produits (admin)'),
        ('products.suspend', 'Suspendre un produit'),
        # Commandes (admin)
        ('orders.manage', 'Gérer les commandes'),
        ('orders.cancel', 'Annuler une commande'),
        # Paiements
        ('payments.refund', 'Rembourser un paiement'),
        # Abonnements - lecture
        ('subscriptions.view', 'Voir les abonnements'),
        # KYC - workflow complet
        ('kyc.view', 'Voir les dossiers KYC'),
        ('kyc.review', 'Commencer la vérification KYC'),
        ('kyc.approve', 'Approuver un dossier KYC'),
        ('kyc.reject', 'Rejeter un dossier KYC'),
        ('kyc.suspend', 'Suspendre un dossier KYC'),
        ('kyc.block', 'Bloquer un dossier KYC'),
        # Livreurs
        ('drivers.view', 'Voir les livreurs'),
        ('drivers.manage', 'Gérer les livreurs'),
        ('drivers.suspend', 'Suspendre un livreur'),
        # Livraisons
        ('deliveries.view', 'Voir les livraisons'),
        ('deliveries.manage', 'Gérer les livraisons'),
        # Plaintes & litiges
        ('complaints.view', 'Voir les plaintes'),
        ('complaints.manage', 'Gérer les plaintes'),
        ('complaints.assign', 'Assigner une plainte'),
        ('complaints.resolve', 'Résoudre une plainte'),
        # Support / tickets
        ('support.view', 'Voir les tickets support'),
        ('support.manage', 'Gérer les tickets support'),
        # Remboursements
        ('refunds.view', 'Voir les remboursements'),
        ('refunds.manage', 'Gérer les remboursements'),
        # Rapports & exports
        ('reports.view', 'Voir les rapports'),
        ('reports.generate', 'Générer un rapport'),
        ('reports.export', 'Exporter un rapport (PDF/CSV/Excel)'),
        # Administrateurs
        ('admins.view', 'Voir les administrateurs'),
        ('admins.manage', 'Gérer les administrateurs'),
        # Paramètres plateforme
        ('settings.view', 'Voir les paramètres'),
        ('settings.manage', 'Modifier les paramètres'),
        # Journal d'audit
        ('audit.view', "Consulter le journal d'audit"),
        # Administration technique / emergency
        ('ops.manage', "Gérer l'administration technique"),
    ]

    permission_objects = {}
    for code, label in permissions:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={'label': label}
        )
        permission_objects[code] = perm

    # 3. Assigner les permissions aux rôles

    # --- ADMIN (legacy) et SUPER_ADMIN : Toutes les permissions ---
    admin_role = role_objects[Role.RoleName.ADMIN]
    super_admin_role = role_objects[Role.RoleName.SUPER_ADMIN]
    for perm in permission_objects.values():
        RolePermission.objects.get_or_create(role=admin_role, permission=perm)
        RolePermission.objects.get_or_create(role=super_admin_role, permission=perm)

    # --- Rôles administrateurs spécialisés (centre de contrôle, spec §42) ---
    def _grant(role_name, codes):
        for code in codes:
            perm = permission_objects.get(code)
            if perm is not None:
                RolePermission.objects.get_or_create(role=role_objects[role_name], permission=perm)

    # ADMIN KYC : vérification d'identité uniquement
    _grant(Role.RoleName.ADMIN_KYC, [
        'view_user', 'view_store', 'view_product',
        'kyc.view', 'kyc.review', 'kyc.approve', 'kyc.reject',
        'kyc.suspend', 'kyc.block',
        'drivers.view', 'deliveries.view',
        'audit.view',
    ])

    # ADMIN SUPPORT : clients, commandes, tickets, plaintes
    _grant(Role.RoleName.ADMIN_SUPPORT, [
        'view_user', 'view_product', 'view_store',
        'view_order', 'orders.manage', 'update_order_status',
        'view_payment',
        'complaints.view', 'complaints.manage', 'complaints.assign', 'complaints.resolve',
        'support.view', 'support.manage',
        'refunds.view',
        'deliveries.view',
    ])

    # ADMIN FINANCE : paiements, abonnements, remboursements, rapports
    _grant(Role.RoleName.ADMIN_FINANCE, [
        'view_user',
        'view_payment', 'manage_payment', 'payments.refund',
        'view_commission', 'manage_commission',
        'subscriptions.view', 'manage_subscription',
        'refunds.view', 'refunds.manage',
        'view_analytics', 'view_detailed_analytics',
        'reports.view', 'reports.generate', 'reports.export',
        'audit.view',
    ])

    # ADMIN MARKETPLACE : vendeurs, boutiques, produits, commandes
    _grant(Role.RoleName.ADMIN_MARKETPLACE, [
        'view_user',
        'sellers.view', 'sellers.edit', 'sellers.suspend', 'sellers.block',
        'view_store', 'edit_store', 'validate_store', 'suspend_store', 'stores.manage',
        'view_product', 'products.manage', 'products.suspend',
        'view_order', 'orders.manage', 'orders.cancel', 'update_order_status',
        'subscriptions.view',
        'complaints.view',
        'deliveries.view',
    ])

    # ADMIN LIVRAISON : livreurs, livraisons, incidents
    _grant(Role.RoleName.ADMIN_DELIVERY, [
        'view_user', 'view_order',
        'drivers.view', 'drivers.manage', 'drivers.suspend',
        'view_delivery', 'deliveries.view', 'deliveries.manage',
        'accept_delivery', 'update_delivery_status',
        'complaints.view', 'complaints.assign', 'complaints.resolve',
    ])

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

    # --- PARTNER : espace partenaire (livraisons, livreurs, tarifs, finances) ---
    partner_role = role_objects[Role.RoleName.PARTNER] if Role.RoleName.PARTNER in role_objects else None
    if partner_role:
        partner_perms = [
            'view_delivery', 'assign_delivery', 'update_delivery_status',
            'view_driver', 'create_driver', 'edit_driver',
            'view_delivery_zone', 'view_order',
        ]
        for code in partner_perms:
            if code in permission_objects:
                RolePermission.objects.get_or_create(role=partner_role, permission=permission_objects[code])
