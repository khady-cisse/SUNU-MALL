"""
Fonctions transverses KYC : contrôle d'accès après vérification,
notifications utilisateur et journal d'audit des actions admin.
"""
from django.conf import settings
from apps.monetization.models import Notification
from apps.users.models import Role
from .models import DriverKYC, KYCAuditLog, SellerKYC


# --- Contrôles d'accès "après KYC" (section 21 de la spec) ---

def seller_kyc_verified(user):
    """Un vendeur ne peut créer de boutique que si son KYC est vérifié (l'admin reste libre)."""
    if user.has_role(Role.RoleName.ADMIN):
        return True
    return SellerKYC.objects.filter(seller=user, status=SellerKYC.Status.VERIFIED).exists()


def driver_kyc_verified(user):
    """Un livreur ne peut accepter de livraisons que si son KYC est vérifié (l'admin reste libre)."""
    if user.has_role(Role.RoleName.ADMIN):
        return True
    return DriverKYC.objects.filter(driver=user, status=DriverKYC.Status.VERIFIED).exists()


# --- Notifications utilisateur (section 20) ---

def _notify(user, subject, message):
    notification = Notification.objects.create(
        user=user,
        channel=Notification.Channel.EMAIL,
        subject=subject,
        message=message,
    )
    notification.send()


def notify_kyc_uploaded(user):
    _notify(
        user,
        subject="🔐 Vérification en cours",
        message=(
            "Merci d'avoir envoyé vos documents.\n"
            "Sunu Mall vérifiera votre identité sous 24 heures.\n"
            "Vous recevrez une notification dès que votre vérification sera terminée."
        ),
    )


def notify_kyc_approved(user):
    _notify(
        user,
        subject="✅ Identité vérifiée",
        message=(
            "Bonjour,\n\n"
            "Votre identité a été vérifiée avec succès par Sunu Mall.\n"
            "Votre espace vendeur est désormais ouvert.\n\n"
            f"Connectez-vous ici : {settings.FRONTEND_URL}/login\n\n"
            "Cordialement,\nL'équipe Sunu Mall"
        ),
    )


def notify_kyc_rejected(user, reason=""):
    message = (
        "Bonjour,\n\n"
        "Nous n'avons pas pu valider votre identité.\n"
        "Renouvelez votre demande et envoyez à nouveau vos documents.\n"
    )
    if reason:
        message += f"\nMotif du rejet : {reason}\n"
    message += f"\nConnectez-vous ici : {settings.FRONTEND_URL}/login\n\nCordialement,\nL'équipe Sunu Mall"
    _notify(user, subject="⚠️ Vérification à refaire", message=message)


# --- Journal d'audit (section 23) ---

def record_kyc_audit(admin, kyc, action):
    """Trace l'action admin. Jamais les images — uniquement des identifiants."""
    KYCAuditLog.objects.create(
        admin=admin,
        kyc_id=str(kyc.id),
        owner_id=str(kyc.owner().id),
        owner_type=kyc.owner_type,
        action=action,
    )