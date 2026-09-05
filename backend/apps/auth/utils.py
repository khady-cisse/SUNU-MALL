"""
Utilitaires pour l'authentification : génération de tokens, envoi d'emails, etc.
"""
import logging

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.conf import settings
from apps.users.models import User

logger = logging.getLogger(__name__)


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """
    Générateur de tokens pour la vérification d'email (hérite de PasswordResetTokenGenerator).
    """
    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{timestamp}{user.is_verified}"


email_verification_token = EmailVerificationTokenGenerator()


def send_verification_email(user: User):
    """
    Envoie un email de vérification à l'utilisateur. Ne lève jamais : un
    échec d'envoi (SMTP injoignable, quota dépassé...) ne doit pas faire
    échouer une inscription déjà créée — le compte reste récupérable via
    l'endpoint `resend-verification`.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)

    verification_url = f"{settings.FRONTEND_URL}/verify-email?uid={uid}&token={token}"

    subject = "Vérifiez votre email - SUNU MALL"
    message = render_to_string('emails/verification_email.txt', {
        'user': user,
        'verification_url': verification_url,
    })
    html_message = render_to_string('emails/verification_email.html', {
        'user': user,
        'verification_url': verification_url,
    })

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception:
        logger.exception("Échec de l'envoi de l'email de vérification pour %s", user.email)
