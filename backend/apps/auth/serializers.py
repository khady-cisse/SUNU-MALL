from rest_framework import serializers
from django.contrib.auth import authenticate
from apps.users.models import User, Role, UserRole

ALLOWED_REGISTRATION_ROLES = {'client', 'merchant', 'driver'}

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    role_name = serializers.ChoiceField(
        choices=[(r, r) for r in sorted(ALLOWED_REGISTRATION_ROLES)],
        write_only=True,
        required=False,
        default='client',
    )

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'phone', 'password', 'role_name')

    def create(self, validated_data):
        role_name = validated_data.pop('role_name', 'client')

        username = validated_data['email']

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

        return user

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
