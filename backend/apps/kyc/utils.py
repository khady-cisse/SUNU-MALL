"""
Fonctions transverses KYC : contrôle d'accès après vérification,
notifications utilisateur, journal d'audit des actions admin, protection
contre la fraude (documents réutilisés) et journal de sécurité.
"""
from django.conf import settings
from apps.monetization.models import Notification
from apps.security.utils import log_security_event
from .models import DriverKYC, KYCAuditLog, SellerKYC


# --- Contrôles d'accès "après KYC" (section 21 de la spec) ---

def seller_kyc_verified(user):
    """Un vendeur ne peut vendre que si son KYC est vérifié (l'admin reste libre).

    Les comptes SUSPENDED ou BLOCKED ne vérifient PAS cette condition : la
    suspension et le blocage coupent immédiatement la capacité à vendre.
    """
    if user.is_admin():
        return True
    return SellerKYC.objects.filter(
        seller=user,
        status=SellerKYC.Status.VERIFIED,
    ).exists()


def seller_kyc_status(user):
    """Statut de vérification du vendeur (None si aucun dossier)."""
    kyc = SellerKYC.objects.filter(seller=user).only("status").first()
    return kyc.status if kyc else None


def seller_account_active(user):
    """Le compte vendeur existe, sa vérification est validée et il n'est ni
    suspendu ni bloqué."""
    return seller_kyc_status(user) == SellerKYC.Status.VERIFIED


def driver_kyc_verified(user):
    """Un livreur ne peut accepter de livraisons que si son KYC est vérifié (l'admin reste libre)."""
    if user.is_admin():
        return True
    return DriverKYC.objects.filter(driver=user, status=DriverKYC.Status.VERIFIED).exists()


# --- Notifications utilisateur (section 20) ---

def _notify(user, subject, message, metadata=None):
    notification = Notification.objects.create(
        user=user,
        channel=Notification.Channel.EMAIL,
        subject=subject,
        message=message,
        metadata=metadata or {},
    )
    notification.send()
    return notification


def notify_kyc_uploaded(user):
    _notify(
        user,
        subject="📥 Documents reçus",
        message=(
            "Bonjour,\n\n"
            "Votre dossier de vérification a bien été reçu par Sunu Mall.\n"
            "Sunu Mall vérifiera votre identité sous 24 heures.\n"
            "Vous recevrez une notification dès que votre vérification sera terminée."
        ),
        metadata={"kind": "kyc_submitted"},
    )


def notify_kyc_under_review(user):
    _notify(
        user,
        subject="🔎 Vérification en cours",
        message=(
            "Bonjour,\n\n"
            "Votre dossier est actuellement en cours de vérification par l'équipe Sunu Mall.\n"
            "Vous recevrez une notification dès que votre vérification sera terminée."
        ),
        metadata={"kind": "kyc_under_review"},
    )


def notify_kyc_submitted(user):
    _notify(
        user,
        subject="📤 Dossier soumis",
        message=(
            "Bonjour,\n\n"
            "Votre dossier de vérification a bien été soumis à Sunu Mall.\n\n"
            "Cordialement,\nL'équipe Sunu Mall"
        ),
        metadata={"kind": "kyc_submitted_to_review"},
    )


def notify_kyc_approved(user):
    _notify(
        user,
        subject="✅ Identité vérifiée",
        message=(
            "Bonjour,\n\n"
            "Félicitations ! Votre identité a été vérifiée.\n"
            "Votre boutique est maintenant active sur Sunu Mall.\n\n"
            f"Connectez-vous ici : {settings.FRONTEND_URL}/merchant\n\n"
            "Cordialement,\nL'équipe Sunu Mall"
        ),
        metadata={"kind": "kyc_approved"},
    )


def notify_kyc_rejected(user, reason=""):
    message = (
        "Bonjour,\n\n"
        "Votre demande de vérification n'a pas été validée.\n"
        "Consultez votre espace pour connaître la raison et soumettre un nouveau dossier.\n"
    )
    if reason:
        message += f"\nMotif : {reason}\n"
    message += f"\nConnectez-vous ici : {settings.FRONTEND_URL}/merchant\n\nCordialement,\nL'équipe Sunu Mall"
    _notify(user, subject="❌ Vérification à refaire", message=message, metadata={"kind": "kyc_rejected"})


def notify_kyc_resubmission(user, reason=""):
    message = (
        "Bonjour,\n\n"
        "Nous avons besoin d'un nouveau dossier pour continuer la vérification "
        "de votre identité.\n"
    )
    if reason:
        message += f"\nMotif : {reason}\n"
    message += (
        "\nMerci de soumettre à nouveau vos documents depuis votre espace vendeur :\n"
        f"{settings.FRONTEND_URL}/merchant\n\nCordialement,\nL'équipe Sunu Mall"
    )
    _notify(user, subject="📄 Veuillez soumettre un nouveau dossier", message=message, metadata={"kind": "kyc_resubmission"})


def notify_kyc_suspended(user, reason=""):
    message = (
        "Bonjour,\n\n"
        "Votre espace vendeur a été temporairement suspendu par Sunu Mall.\n"
    )
    if reason:
        message += f"\nMotif : {reason}\n"
    message += "\nContactez le support pour toute question.\n\nCordialement,\nL'équipe Sunu Mall"
    _notify(user, subject="⏸️ Compte vendeur suspendu", message=message, metadata={"kind": "kyc_suspended"})


def notify_kyc_blocked(user, reason=""):
    message = (
        "Bonjour,\n\n"
        "Votre compte vendeur a été bloqué définitivement par Sunu Mall "
        "pour non-respect des conditions d'utilisation.\n"
    )
    if reason:
        message += f"\nMotif : {reason}\n"
    message += "\nCordialement,\nL'équipe Sunu Mall"
    _notify(user, subject="🚫 Compte vendeur bloqué", message=message, metadata={"kind": "kyc_blocked"})


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


# --- Journal de sécurité (spec §16) ---

def log_kyc_security(user, action, request=None, metadata=None):
    log_security_event(user, action, request, metadata)


# --- Protection contre la fraude (spec §15) ---

def _document_fingerprint(uploaded_file):
    """
    Empreinte SHA-256 du fichier brut (recto du document). Permet de détecter
    qu'un même document a été soumis sur plusieurs comptes — sans stocker le
    document lui-même ailleurs que dans le stockage privé.
    """
    import hashlib

    uploaded_file.seek(0)
    digest = hashlib.sha256(uploaded_file.read()).hexdigest()
    uploaded_file.seek(0)
    return digest


def fraud_flags_for_seller(seller):
    """Contrôles simples de fraude (V1, spec §15) : retourne une liste de
    alertes destinée à l'admin. Aucun comportement d'IA — juste des
    recoupements en base. Détecte :

    - même numéro de téléphone sur plusieurs comptes ;
    - même document d'identité (empreinte) soumis à plusieurs comptes ;
    - plusieurs comptes vendeurs avec la même adresse email.
    L'email étant unique en base, le troisième cas est couvert côté modèle.
    """
    from apps.users.models import User

    flags = []
    kyc = SellerKYC.objects.filter(seller=seller).only(
        "seller_id", "document_hash", "address", "status"
    ).first()

    if kyc is None:
        return flags

    # 1. Même document réutilisé sur un autre compte vendeur.
    if kyc.document_hash:
        reused = (
            SellerKYC.objects
            .filter(document_hash=kyc.document_hash)
            .exclude(seller_id=seller.id)
            .select_related("seller")
        )
        for other in reused[:10]:
            flags.append({
                "code": "document_reused",
                "message": f"Document identique au compte {other.seller.email} (dossier {other.id}).",
            })

    # 2. Le téléphone du compte correspond à un autre compte vendeur.
    same_phone = (
        User.objects
        .filter(phone__iexact=seller.phone)
        .exclude(id=seller.id)
    )
    for other in same_phone[:10]:
        flags.append({
            "code": "phone_reused",
            "message": f"Numéro de téléphone partagé avec le compte {other.email}.",
        })

    return flags


def check_reused_document(new_hash, exclude_seller):
    """Vrai si ce document a déjà été soumis par un autre vendeur."""
    if not new_hash:
        return False
    return SellerKYC.objects.filter(
        document_hash=new_hash
    ).exclude(seller_id=exclude_seller.id).exists()