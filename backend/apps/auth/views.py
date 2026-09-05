from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.core.exceptions import ValidationError
from .serializers import (
    RegisterSerializer, LoginSerializer, ResendVerificationSerializer,
    GuestCheckoutSerializer, SetPasswordSerializer,
)
from .utils import email_verification_token, send_verification_email
from apps.users.models import User


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

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Envoyer l'email de vérification
        send_verification_email(user)

        roles = [ur.role.name for ur in user.user_roles.select_related('role')]

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
            },
            "access": None,
            "refresh": None,
            "message": "Inscription réussie ! Vérifiez votre email pour activer votre compte."
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
