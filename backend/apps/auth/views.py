import logging
from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.conf import settings
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from .serializers import (
    RegisterSerializer, LoginSerializer, ResendVerificationSerializer,
    GuestCheckoutSerializer, SetPasswordSerializer, ChangePasswordSerializer,
)
from .utils import email_verification_token, send_verification_email
from apps.security.utils import log_security_event
from apps.users.models import PhoneOTP, User

logger = logging.getLogger(__name__)


class AuthAnonRateThrottle(AnonRateThrottle):
    rate = "10/min"

    def allow_request(self, request, view):
        # En dev (AUTH_ANON_THROTTLE_RATE = None dans config/settings/dev.py)
        # le throttle est inactif : pensé pour la production (protéger
        # /login, /register, /token... du brute-force). On ne s'appuie PAS sur
        # settings.DEBUG car Django force DEBUG=False pendant `manage.py test`.
        if settings.AUTH_ANON_THROTTLE_RATE is None:
            return True
        return super().allow_request(request, view)


class VerifiedTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Empêche l'obtention de JWT via l'endpoint SimpleJWT tant que l'email
    de l'utilisateur n'a pas été confirmé.
    """

    def validate(self, attrs):
        authenticate_kwargs = {
            self.username_field: attrs[self.username_field],
            "password": attrs["password"],
        }
        request = self.context.get("request")
        if request is not None:
            authenticate_kwargs["request"] = request

        self.user = authenticate(**authenticate_kwargs)

        if not api_settings.USER_AUTHENTICATION_RULE(self.user):
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                code="no_active_account",
            )

        if not self.user.is_verified:
            raise AuthenticationFailed(
                "Veuillez vérifier votre email avant de vous connecter.",
                code="email_not_verified",
            )

        refresh = self.get_token(self.user)
        data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }

        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, self.user)

        # Journal de sécurité §16 : connexion depuis l'endpoint SimpleJWT.
        log_security_event(self.user, "LOGIN", request, metadata={"via": "token"})

        return data


class VerifiedTokenObtainPairView(TokenObtainPairView):
    serializer_class = VerifiedTokenObtainPairSerializer
    throttle_classes = [AuthAnonRateThrottle]

class RegisterView(generics.CreateAPIView):
    """
    Inscription d'un nouvel utilisateur (Acheteur, Vendeur, etc.).
    Le rôle par défaut est 'client'.
    Envoie un email de vérification.
    """
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthAnonRateThrottle]
    # L'inscription vendeur embarque les pièces d'identité : on accepte le
    # multipart en prévision, sinon DRF rejette les fichiers (400).
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Envoyer l'email de vérification
        send_verification_email(user)

        roles = [ur.role.name for ur in user.user_roles.select_related('role')]
        is_merchant = 'merchant' in roles

        return Response({
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "phone": user.phone,
                "roles": roles,
                "is_verified": user.is_verified,
                "has_password": True,
                "must_change_password": user.must_change_password,
            },
            "access": None,
            "refresh": None,
            "message": (
                "Inscription réussie ! Vérifiez votre email pour activer votre compte."
                if not is_merchant
                else "Inscription réussie ! Vérifiez votre email, puis notre équipe "
                     "examinera vos pièces d'identité avant l'ouverture de votre boutique."
            ),
        }, status=status.HTTP_201_CREATED)

class LoginView(generics.GenericAPIView):
    """
    Connexion d'un utilisateur existant avec email et mot de passe.
    Retourne des tokens JWT.
    """
    serializer_class = LoginSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthAnonRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data
        
        if not user.is_verified:
            return Response({
                "error": "Veuillez vérifier votre email avant de vous connecter."
            }, status=status.HTTP_403_FORBIDDEN)
        
        refresh = RefreshToken.for_user(user)
        
        roles = [ur.role.name for ur in user.user_roles.select_related('role')]

        # Journal de sécurité §16 : connexion réussie (avec l'IP d'origine).
        log_security_event(
            user, "LOGIN", request,
            metadata={"via": "login", "roles": roles},
        )
        
        return Response({
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "phone": user.phone,
                "roles": roles,
                "is_verified": user.is_verified,
                "has_password": True,
                "must_change_password": user.must_change_password,
            },
            "access": str(refresh.access_token),
            "refresh": str(refresh)
        })

class VerifyEmailView(APIView):
    """
    Vérifie l'email de l'utilisateur via le token envoyé par email.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        uidb64 = request.query_params.get('uid')
        token = request.query_params.get('token')
        
        if not uidb64 or not token:
            return Response({
                "error": "UID et token requis."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({
                "error": "Lien invalide ou expiré."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Idempotent : le hash du token inclut is_verified (voir
        # EmailVerificationTokenGenerator), donc le même lien redevient
        # "invalide" dès la première vérification réussie. Sans ce
        # court-circuit, un second appel légitime — React StrictMode qui
        # déclenche l'effet deux fois en dev, un client mail qui pré-visite
        # le lien pour le scanner, l'utilisateur qui clique deux fois —
        # afficherait à tort un échec alors que le compte est déjà activé.
        if user.is_verified:
            return Response({
                "message": "Email déjà vérifié. Votre compte est activé."
            }, status=status.HTTP_200_OK)

        if email_verification_token.check_token(user, token):
            user.is_verified = True
            user.save()
            return Response({
                "message": "Email vérifié avec succès ! Votre compte est activé."
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                "error": "Lien invalide ou expiré."
            }, status=status.HTTP_400_BAD_REQUEST)

class ResendVerificationEmailView(generics.GenericAPIView):
    """
    Renvoie l'email de vérification à l'utilisateur.
    """
    serializer_class = ResendVerificationSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthAnonRateThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # On ne révèle pas si l'email existe ou non pour des raisons de sécurité
            return Response({
                "message": "Si cet email est associé à un compte, un email de vérification a été envoyé."
            }, status=status.HTTP_200_OK)
        
        if user.is_verified:
            # Ne pas révéler l'état du compte : même réponse générique que
            # pour un email inconnu, pour ne pas faciliter l'énumération.
            return Response({
                "message": "Si cet email est associé à un compte, un email de vérification a été envoyé."
            }, status=status.HTTP_200_OK)
        
        send_verification_email(user)
        return Response({
            "message": "Si cet email est associé à un compte, un email de vérification a été envoyé."
        }, status=status.HTTP_200_OK)


class GuestCheckoutView(generics.GenericAPIView):
    """
    Point d'entrée "achat sans compte" : crée un compte client sans mot de
    passe à partir des seules infos de contact et retourne directement des
    JWT, sans passer par la vérification d'email exigée par /login/. Le
    client ne voit jamais de formulaire d'inscription avant de payer.
    """
    serializer_class = GuestCheckoutSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthAnonRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        roles = [ur.role.name for ur in user.user_roles.select_related('role')]

        # Journal de sécurité §16 : achat sans compte (création de compte).
        log_security_event(user, "LOGIN", request, metadata={"via": "guest_checkout", "roles": roles})

        return Response({
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "phone": user.phone,
                "roles": roles,
                "is_verified": user.is_verified,
                "has_password": user.has_usable_password(),
            },
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        })


class SetPasswordView(generics.GenericAPIView):
    """Convertit le compte invité de l'utilisateur connecté en compte complet (avec mot de passe)."""
    serializer_class = SetPasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['password'])
        request.user.save()
        send_verification_email(request.user)
        return Response({
            "message": "Mot de passe défini. Vérifiez votre email pour activer toutes les fonctionnalités.",
        })


class ChangePasswordView(generics.GenericAPIView):
    """Change le mot de passe de l'utilisateur connecté (ancien + nouveau).

    Pour les comptes créés par un administrateur (livreurs), le premier
    changement de mot de passe lève aussi l'obligation `must_change_password`,
    ce qui débloque l'accès complet à l'espace livreur.
    """
    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data['current_password']):
            return Response(
                {"error": "Mot de passe actuel incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(serializer.validated_data['new_password'])
        if user.must_change_password:
            user.must_change_password = False
        user.save()
        # Journal de sécurité §16 : changement du mot de passe du compte.
        log_security_event(user, "PASSWORD_CHANGE", request)
        return Response({"message": "Mot de passe modifié avec succès."})


def _send_phone_otp_notification(user, phone, plaintext_code):
    """Envoi du code par SMS via le canal Notification (aucun fournisseur
    branché à ce jour → la notification reste tracée, jamais réellement
    envoyée). En dev/test avec PHONE_OTP_REVEAL_CODE, le code est aussi
    loggé en console pour faciliter le développement."""
    from apps.monetization.models import Notification

    notification = Notification.objects.create(
        user=user,
        channel=Notification.Channel.SMS,
        subject="Code de vérification SUNU MALL",
        message=f"Votre code de vérification est : {plaintext_code}. "
                "Ne le partagez avec personne.",
        metadata={"kind": "phone_otp", "phone": phone},
    )
    notification.send()
    if settings.PHONE_OTP_REVEAL_CODE:
        logger.info("OTP téléphone pour %s (%s) : %s", user.email, phone, plaintext_code)
    return notification


class RequestPhoneOTPView(APIView):
    """
    POST /api/auth/request-phone-otp/
    Envoie un code OTP à 6 chiffres au numéro de téléphone du compte connecté.

    Un compte déjà confirmé reçoit une erreur (pas de re-envoi inutile) ;
    un nouveau code invalide le précédent (un seul code actif à la fois).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.phone_verified:
            raise ValidationError({"phone": "Ce numéro est déjà vérifié."})
        if not user.phone:
            raise ValidationError({"phone": "Aucun numéro de téléphone sur ce compte."})

        code = PhoneOTP.generate_code()
        expires_at = timezone.now() + timedelta(minutes=settings.PHONE_OTP_TTL_MINUTES)

        # Un seul code actif : on invalide les précédents du même numéro.
        PhoneOTP.objects.filter(user=user, phone=user.phone, verified_at__isnull=True).update(expires_at=timezone.now())

        otp = PhoneOTP.objects.create(
            user=user,
            phone=user.phone,
            code_hash=PhoneOTP._hash(code),
            expires_at=expires_at,
        )
        _send_phone_otp_notification(user, user.phone, code)

        log_security_event(user, "PHONE_CHANGE", request, metadata={"phone": user.phone, "action": "request_otp"})

        data = {
            "message": "Code de vérification envoyé par SMS.",
            "expires_in_minutes": settings.PHONE_OTP_TTL_MINUTES,
            "attempts_remaining": settings.PHONE_OTP_MAX_ATTEMPTS,
        }
        if settings.PHONE_OTP_REVEAL_CODE:
            data["debug_code"] = code
        return Response(data, status=status.HTTP_201_CREATED)


class VerifyPhoneOTPView(APIView):
    """
    POST /api/auth/verify-phone-otp/
    Confirme le numéro de téléphone avec le code reçu. ({"code": "123456"})

    Limite le nombre d'essais (`PHONE_OTP_MAX_ATTEMPTS`) et refuse un code
    expiré. Une fois vérifié, `phone_verified` reste acquis sur le compte.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        code = str((request.data or {}).get("code", "")).strip()
        if not code or not code.isdigit():
            raise ValidationError({"code": "Code OTP requis (6 chiffres)."})

        otp = PhoneOTP.objects.filter(user=user, verified_at__isnull=True).first()
        if otp is None:
            raise ValidationError({"code": "Aucun code en attente. Redemandez-en un."})

        if not otp.valid_for_verification(settings.PHONE_OTP_MAX_ATTEMPTS):
            raise ValidationError({"code": "Code expiré ou trop d'essais. Redemandez-en un."})

        if not otp.verify(code, settings.PHONE_OTP_MAX_ATTEMPTS):
            remaining = max(0, settings.PHONE_OTP_MAX_ATTEMPTS - otp.attempts)
            raise ValidationError({"code": f"Code incorrect. {remaining} essai(s) restant(s)."})

        # Consomme le code et confirme durablement le numéro du compte.
        user.phone_verified = True
        user.phone_verified_at = timezone.now()
        user.save(update_fields=["phone_verified", "phone_verified_at", "updated_at"])

        log_security_event(user, "PHONE_CHANGE", request, metadata={"phone": user.phone, "action": "verify_otp"})

        return Response({
            "message": "Numéro de téléphone vérifié.",
            "phone_verified": True,
            "phone": user.phone,
        })


class LogoutView(APIView):
    """
    POST /api/auth/logout/
    Révoque le refresh token fourni (blacklist SimpleJWT) et journalise la
    déconnexion dans le journal de sécurité §16.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = (request.data or {}).get("refresh", "")
        if not refresh:
            raise ValidationError({"refresh": "Le token refresh est requis."})
        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except Exception as exc:  # noqa: BLE001 - token déjà périmé/révoqué : rien à blacklister
            logger.info("Logout d'un refresh déjà invalide : %s", str(exc)[:80])

        log_security_event(request.user, "LOGOUT", request)
        return Response({"message": "Déconnecté."})
