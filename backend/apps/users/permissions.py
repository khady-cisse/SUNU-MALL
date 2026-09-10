"""
Permissions personnalisées pour le RBAC de SUNU MALL.
"""
from rest_framework import permissions
from apps.users.models import Role


class IsAdmin(permissions.BasePermission):
    """Permission pour les administrateurs (rôle maître ou spécialisé)."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_admin()
        )


class IsMerchant(permissions.BasePermission):
    """Permission pour les commerçants uniquement."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.has_role(Role.RoleName.MERCHANT)
        )


class IsClient(permissions.BasePermission):
    """Permission pour les clients uniquement."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.has_role(Role.RoleName.CLIENT)
        )


class IsDriver(permissions.BasePermission):
    """Permission pour les livreurs uniquement."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.has_role(Role.RoleName.DRIVER)
        )


class HasPermission(permissions.BasePermission):
    """
    Permission générique qui vérifie si l'utilisateur a une permission spécifique.
    Utilisation:
        permission_classes = [HasPermission]
        required_permission = 'view_product'
    """
    required_permission = None

    def has_permission(self, request, view):
        if not self.required_permission:
            raise NotImplementedError("Veuillez définir 'required_permission' sur la vue.")
        
        return (
            request.user
            and request.user.is_authenticated
            and request.user.has_permission(self.required_permission)
        )


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Permission qui vérifie si l'utilisateur est le propriétaire de l'objet ou admin.
    L'objet doit avoir un attribut 'owner' ou 'user' ou une méthode get_owner().
    """
    def has_object_permission(self, request, view, obj):
        # Admin peut tout faire
        if request.user.is_admin():
            return True
        
        # Vérifier si c'est le propriétaire
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        if hasattr(obj, 'user'):
            return obj.user == request.user
        if hasattr(obj, 'get_owner'):
            return obj.get_owner() == request.user
        return False


class IsStoreOwnerOrAdmin(permissions.BasePermission):
    """
    Vérifie si l'utilisateur est le propriétaire de la boutique associée à l'objet ou admin.
    L'objet doit avoir un attribut 'store' ou une méthode get_store().
    """
    def has_object_permission(self, request, view, obj):
        # Admin peut tout faire
        if request.user.is_admin():
            return True
        
        # Récupérer la boutique
        store = None
        if hasattr(obj, 'store'):
            store = obj.store
        elif hasattr(obj, 'get_store'):
            store = obj.get_store()
        
        if store:
            return store.owner == request.user
        return False
