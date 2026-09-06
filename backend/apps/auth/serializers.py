from django.db import transaction
from rest_framework import serializers
from django.contrib.auth import authenticate
from apps.kyc.serializers import KYC_DOCUMENT_TYPES
from apps.users.models import User, Role, UserRole

ALLOWED_REGISTRATION_ROLES = {'client', 'merchant', 'driver'}

# Pièces d'identité exigées à l'inscription d'un compte vendeur. Le dossier
# KYC est ensuite examiné par l'administration avant toute ouverture de
# boutique (voir apps/kyc/utils.seller_kyc_verified et apps/catalog).
_KYC_MAX_SIZE = 8 * 1024 * 1024


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    role_name = serializers.ChoiceField(
        choices=[(r, r) for r in sorted(ALLOWED_REGISTRATION_ROLES)],
        write_only=True,
        required=False,
        default='client',
    )
    # Pièces d'identité — obligatoires SEULEMENT pour les vendeurs (validation
    # côte à côte dans validate()).
    document_type = serializers.ChoiceField(
        choices=[(value, label) for value, label in KYC_DOCUMENT_TYPES],
        write_only=True,
        required=False,
    )
    document_front = serializers.FileField(write_only=True, required=False)
    document_back = serializers.FileField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'phone', 'password',
                  'role_name', 'document_type', 'document_front', 'document_back')

    def validate_document_front(self, value):
        return self._validate_document(value)

    def validate_document_back(self, value):
        return self._validate_document(value)

    def validate(self, attrs):
        role_name = attrs.get('role_name', 'client')

        if role_name == 'merchant':
            missing = [
                name for name in ('document_type', 'document_front', 'document_back')
                if name not in attrs
            ]
            if missing:
                raise serializers.ValidationError({
                    'detail': (
                        "La vérification d'identité est obligatoire pour un compte "
                        "vendeur. Pièce manquante : " + ', '.join(missing) + "."
                    )
                })
        else:
            provided = [
                name for name in ('document_type', 'document_front', 'document_back')
                if name in self.initial_data
            ]
            if provided:
                raise serializers.ValidationError({
                    'detail': "Les pièces d'identité ne concernent que les comptes vendeurs."
                })

        return attrs

    def create(self, validated_data):
        role_name = validated_data.pop('role_name', 'client')

        username = validated_data['email']

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=validated_data['email'],
                password=validated_data['password'],
                first_name=validated_data.get('first_name', ''),
                last_name=validated_data.get('last_name', ''),
                phone=validated_data.get('phone', '')
            )

            role, _ = Role.objects.get_or_create(name=role_name)
            UserRole.objects.create(user=user, role=role)

            if role_name == 'merchant':
                self._create_seller_kyc(user, validated_data)

            return user

    @staticmethod
    def _create_seller_kyc(user, data):
        """Crée le dossier d'identité du vendeur dès l'inscription (PENDING)."""
        from django.utils import timezone
        from apps.kyc.models import SellerKYC
        from apps.kyc.storage import save_document

        kyc = SellerKYC.objects.create(seller=user)
        kyc.document_type = data['document_type']
        kyc.document_front = save_document(kyc, 'front', data['document_front'])
        kyc.document_back = save_document(kyc, 'back', data['document_back'])
        kyc.status = SellerKYC.Status.PENDING
        kyc.submitted_at = timezone.now()
        kyc.save(update_fields=[
            'document_type', 'document_front', 'document_back',
            'status', 'submitted_at', 'updated_at',
        ])

    @staticmethod
    def _validate_document(value):
        if value.size > _KYC_MAX_SIZE:
            raise serializers.ValidationError("Chaque pièce doit faire moins de 8 Mo.")
        return value

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        if email and password:
            user = authenticate(request=self.context.get('request'), email=email, password=password)
            if not user:
                raise serializers.ValidationError("Identifiants incorrects.", code='authorization')
        else:
            raise serializers.ValidationError("Email et mot de passe requis.", code='authorization')

        if not user.is_active:
            raise serializers.ValidationError("Ce compte est désactivé.", code='authorization')
            
        return user

class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class GuestCheckoutSerializer(serializers.Serializer):
    """
    Crée (ou réutilise) silencieusement un compte client sans mot de passe,
    pour permettre un achat sans étape d'inscription visible avant paiement.
    """
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    phone = serializers.CharField(max_length=30)

    def validate_email(self, value):
        existing = User.objects.filter(email=value).first()
        if existing and existing.has_usable_password():
            raise serializers.ValidationError(
                "Cet email est déjà associé à un compte. Merci de vous connecter."
            )
        return value

    def save(self):
        data = self.validated_data
        user = User.objects.filter(email=data['email']).first()
        if user:
            user.first_name = data['first_name']
            user.last_name = data.get('last_name', '')
            user.phone = data['phone']
            user.save()
        else:
            user = User.objects.create_user(
                username=data['email'],
                email=data['email'],
                first_name=data['first_name'],
                last_name=data.get('last_name', ''),
                phone=data['phone'],
            )
            user.set_unusable_password()
            user.save()
            role, _ = Role.objects.get_or_create(name='client')
            UserRole.objects.create(user=user, role=role)
        return user


class SetPasswordSerializer(serializers.Serializer):
    """Transforme un compte invité (sans mot de passe) en compte complet."""
    password = serializers.CharField(write_only=True, min_length=8)


class ChangePasswordSerializer(serializers.Serializer):
    """Changement de mot de passe (ancien + confirmation)."""
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError("La confirmation ne correspond pas au nouveau mot de passe.")
        return attrs
