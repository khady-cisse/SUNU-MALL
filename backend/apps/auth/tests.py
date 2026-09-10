"""
Tests unitaires pour l'application auth.
"""
import shutil
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from apps.kyc.models import SellerKYC
from apps.users.models import User, Role, UserRole
from apps.auth.utils import email_verification_token, send_verification_email
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

mkdtemp = tempfile.mkdtemp


class AuthTests(TestCase):
    def setUp(self):
        """
        Configuration initiale des tests.
        """
        self.client = APIClient()
        self.register_url = reverse('auth_register')
        self.login_url = reverse('auth_login')
        self.verify_email_url = reverse('auth_verify_email')
        self.resend_verification_url = reverse('auth_resend_verification')
        self.token_url = reverse('token_obtain_pair')
        self.token_refresh_url = reverse('token_refresh')
        self.token_verify_url = reverse('token_verify')
        self.token_blacklist_url = reverse('token_blacklist')
        
        # Créer les rôles par défaut
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        Role.objects.get_or_create(name=Role.RoleName.MERCHANT)
        Role.objects.get_or_create(name=Role.RoleName.DRIVER)
        Role.objects.get_or_create(name=Role.RoleName.ADMIN)

    def create_user_with_role(self, *, email='test@example.com', password='testpassword123',
                              role_name=Role.RoleName.CLIENT, is_verified=False,
                              is_active=True, username='testuser'):
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_active=is_active,
        )
        user.is_verified = is_verified
        user.save()
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def test_register_user_success(self):
        """
        Teste l'inscription réussie d'un utilisateur.
        """
        data = {
            'email': 'test@example.com',
            'password': 'testpassword123',
            'first_name': 'Test',
            'last_name': 'User',
            'phone': '+221771234567',
            'role_name': 'client'
        }

        with patch('apps.auth.views.send_verification_email') as mocked_send:
            response = self.client.post(self.register_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIsNone(response.data['access'])
        self.assertIsNone(response.data['refresh'])
        self.assertEqual(response.data['user']['email'], data['email'])
        self.assertEqual(response.data['user']['roles'], ['client'])
        mocked_send.assert_called_once()
        
        user = User.objects.get(email=data['email'])
        self.assertFalse(user.is_verified)
        self.assertTrue(user.check_password(data['password']))

    def test_register_user_missing_fields(self):
        """
        Teste l'inscription avec des champs manquants.
        """
        data = {
            'email': 'test@example.com',
            # Mot de passe manquant
        }
        
        response = self.client.post(self.register_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_login_user_unverified(self):
        """
        Teste la connexion avec un email non vérifié.
        """
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )
        role = Role.objects.get(name=Role.RoleName.CLIENT)
        UserRole.objects.create(user=user, role=role)
        
        data = {
            'email': 'test@example.com',
            'password': 'testpassword123'
        }
        
        response = self.client.post(self.login_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('error', response.data)

    def test_login_user_verified(self):
        """
        Teste la connexion avec un email vérifié.
        """
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )
        user.is_verified = True
        user.save()
        
        role = Role.objects.get(name=Role.RoleName.CLIENT)
        UserRole.objects.create(user=user, role=role)
        
        data = {
            'email': 'test@example.com',
            'password': 'testpassword123'
        }
        
        response = self.client.post(self.login_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['email'], data['email'])

    def test_login_wrong_password(self):
        """
        Teste la connexion avec un mauvais mot de passe.
        """
        self.create_user_with_role(is_verified=True)

        data = {
            'email': 'test@example.com',
            'password': 'wrongpassword'
        }
        
        response = self.client.post(self.login_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)

    def test_login_nonexistent_user(self):
        """
        Teste la connexion avec un utilisateur inexistant.
        """
        data = {
            'email': 'nonexistent@example.com',
            'password': 'wrongpassword'
        }

        response = self.client.post(self.login_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)

    def test_login_inactive_user(self):
        """
        Teste la connexion avec un utilisateur inactif.
        """
        self.create_user_with_role(
            is_verified=True,
            is_active=False,
            email='inactive@example.com',
            username='inactiveuser',
        )

        response = self.client.post(self.login_url, {
            'email': 'inactive@example.com',
            'password': 'testpassword123'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)

    def test_token_obtain_pair_user_unverified(self):
        """
        Teste que l'endpoint SimpleJWT refuse un utilisateur non vérifié.
        """
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )

        response = self.client.post(self.token_url, {
            'email': user.email,
            'password': 'testpassword123'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data['detail'],
            "Veuillez vérifier votre email avant de vous connecter."
        )

    def test_token_obtain_pair_user_verified(self):
        """
        Teste que l'endpoint SimpleJWT fonctionne pour un utilisateur vérifié.
        """
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )
        user.is_verified = True
        user.save()

        response = self.client.post(self.token_url, {
            'email': user.email,
            'password': 'testpassword123'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_token_refresh_success(self):
        """
        Teste le refresh d'un JWT valide.
        """
        user = self.create_user_with_role(
            is_verified=True,
            email='refresh@example.com',
            username='refreshuser',
        )

        token_response = self.client.post(self.token_url, {
            'email': user.email,
            'password': 'testpassword123'
        }, format='json')

        response = self.client.post(self.token_refresh_url, {
            'refresh': token_response.data['refresh']
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_token_verify_success(self):
        """
        Teste la vérification d'un access token valide.
        """
        user = self.create_user_with_role(
            is_verified=True,
            email='verifytoken@example.com',
            username='verifytokenuser',
        )

        token_response = self.client.post(self.token_url, {
            'email': user.email,
            'password': 'testpassword123'
        }, format='json')

        response = self.client.post(self.token_verify_url, {
            'token': token_response.data['access']
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_token_blacklist_revokes_refresh_token(self):
        """
        Teste la mise en blacklist d'un refresh token.
        """
        user = self.create_user_with_role(
            is_verified=True,
            email='blacklist@example.com',
            username='blacklistuser',
        )

        token_response = self.client.post(self.token_url, {
            'email': user.email,
            'password': 'testpassword123'
        }, format='json')
        refresh_token = token_response.data['refresh']

        blacklist_response = self.client.post(self.token_blacklist_url, {
            'refresh': refresh_token
        }, format='json')
        refresh_response = self.client.post(self.token_refresh_url, {
            'refresh': refresh_token
        }, format='json')

        self.assertEqual(blacklist_response.status_code, status.HTTP_200_OK)
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_verify_email_success(self):
        """
        Teste la vérification d'email réussie.
        """
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )
        
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)
        
        response = self.client.get(self.verify_email_url, {'uid': uid, 'token': token})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        
        user.refresh_from_db()
        self.assertTrue(user.is_verified)

    def test_verify_email_same_token_reused_after_verified_is_idempotent(self):
        """
        Un second appel avec le même lien, une fois le compte déjà vérifié,
        renvoie un succès (idempotent) plutôt qu'une erreur — sans ça, un
        double déclenchement légitime (React StrictMode en dev, un client
        mail qui pré-visite le lien pour le scanner) affiche à tort un échec
        alors que la vérification a bien eu lieu.
        """
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)

        first_response = self.client.get(self.verify_email_url, {'uid': uid, 'token': token})
        second_response = self.client.get(self.verify_email_url, {'uid': uid, 'token': token})

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertIn('message', second_response.data)

    def test_verify_email_invalid_token(self):
        """
        Teste la vérification d'email avec un token invalide.
        """
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )
        
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        invalid_token = 'invalidtoken123'
        
        response = self.client.get(self.verify_email_url, {'uid': uid, 'token': invalid_token})
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        
        user.refresh_from_db()
        self.assertFalse(user.is_verified)

    def test_verify_email_expired_token(self):
        """
        Teste la vérification d'email avec un token expiré.
        """
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)
        current_seconds = email_verification_token._num_seconds(email_verification_token._now())

        with patch.object(
            email_verification_token,
            '_num_seconds',
            return_value=current_seconds + settings.PASSWORD_RESET_TIMEOUT + 1,
        ):
            response = self.client.get(self.verify_email_url, {'uid': uid, 'token': token})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

        user.refresh_from_db()
        self.assertFalse(user.is_verified)

    def test_resend_verification_email(self):
        """
        Teste le renvoi de l'email de vérification.
        """
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )
        
        data = {'email': 'test@example.com'}
        with patch('apps.auth.views.send_verification_email') as mocked_send:
            response = self.client.post(self.resend_verification_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        mocked_send.assert_called_once_with(user)

    def test_resend_verification_email_already_verified(self):
        """
        Un compte déjà vérifié reçoit la même réponse générique qu'un email
        inconnu : on ne révèle pas l'état du compte (anti-énumération).
        """
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )
        user.is_verified = True
        user.save()
        
        data = {'email': 'test@example.com'}
        response = self.client.post(self.resend_verification_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_verification_email_helper(self):
        """
        Teste l'envoi réel de l'email de vérification via le helper existant.
        """
        user = User(
            username='testuser',
            email='test@example.com',
            first_name='Test'
        )

        send_verification_email(user)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Vérifiez votre email - SUNU MALL")
        self.assertIn('/verify-email?uid=', mail.outbox[0].body)


class MerchantRegistrationIdentityTests(TestCase):
    """
    L'inscription d'un compte vendeur exige une pièce d'identité : le dossier
    SellerKYC est créé immédiatement (PENDING) pour examen par l'admin.
    Les comptes client ne doivent rien transporter de tel.
    """

    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse('auth_register')
        Role.objects.get_or_create(name=Role.RoleName.MERCHANT)
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        self.tmp = mkdtemp()
        self.storage_override = override_settings(
            KYC_STORAGE_BACKEND="fs",
            KYC_STORAGE_LOCATION=self.tmp,
        )
        self.storage_override.enable()

    def tearDown(self):
        self.storage_override.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _pdf(name="id_front.pdf"):
        return SimpleUploadedFile(name, b"%PDF-1.4 fake-pdf-content", content_type="application/pdf")

    def _base_payload(self, role="merchant", email="seller@example.com"):
        return {
            "email": email,
            "password": "testpassword123",
            "first_name": "Awa",
            "last_name": "Diop",
            "phone": "+221771234567",
            "role_name": role,
        }

    def test_merchant_register_without_identity_documents_is_400(self):
        with patch('apps.auth.views.send_verification_email') as mocked_send:
            response = self.client.post(self.register_url, self._base_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(SellerKYC.objects.count(), 0)
        mocked_send.assert_not_called()

    def test_merchant_register_partial_documents_is_400(self):
        payload = self._base_payload()
        payload["document_type"] = "cni"
        payload["document_front"] = self._pdf("front.pdf")
        with patch('apps.auth.views.send_verification_email') as mocked_send:
            response = self.client.post(self.register_url, payload, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 0)
        mocked_send.assert_not_called()

    def test_merchant_register_with_identity_documents_creates_pending_kyc(self):
        payload = self._base_payload()
        payload.update({
            "document_type": "cni",
            "document_front": self._pdf("front.pdf"),
            "document_back": self._pdf("back.pdf"),
        })
        with patch('apps.auth.views.send_verification_email') as mocked_send:
            response = self.client.post(self.register_url, payload, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["roles"], ["merchant"])
        self.assertIn("pièces d'identité", response.data["message"])
        mocked_send.assert_called_once()

        user = User.objects.get(email=payload["email"])
        kyc = SellerKYC.objects.get(seller=user)
        self.assertEqual(kyc.status, SellerKYC.Status.PENDING)
        self.assertIsNotNone(kyc.submitted_at)
        self.assertTrue(kyc.document_front.startswith("kyc/sellers/"))
        self.assertTrue(kyc.document_front.endswith(".pdf"))
        self.assertNotEqual(kyc.document_front, kyc.document_back)

    def test_client_register_with_documents_is_rejected(self):
        payload = self._base_payload(role="client", email="client@example.com")
        payload.update({
            "document_type": "cni",
            "document_front": self._pdf("front.pdf"),
            "document_back": self._pdf("back.pdf"),
        })
        with patch('apps.auth.views.send_verification_email') as mocked_send:
            response = self.client.post(self.register_url, payload, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ne concernent que les comptes vendeurs", str(response.data))
        self.assertEqual(User.objects.count(), 0)
        mocked_send.assert_not_called()

    def test_client_register_plain_json_still_works(self):
        payload = self._base_payload(role="client", email="client@example.com")
        del payload["role_name"]
        with patch('apps.auth.views.send_verification_email') as mocked_send:
            response = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email=payload["email"])
        self.assertFalse(SellerKYC.objects.filter(seller=user).exists())
        mocked_send.assert_called_once()


class ChangePasswordTests(TestCase):
    """Changement de mot de passe et lever de l'obligation initiale."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="driver@example.com",
            email="driver@example.com",
            password="testpassword123",
            is_verified=True,
            must_change_password=True,
        )
        Role.objects.get_or_create(name=Role.RoleName.DRIVER)
        UserRole.objects.create(user=self.user, role=Role.objects.get(name=Role.RoleName.DRIVER))

    def test_change_password_clears_must_change_password(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/auth/change-password/",
            {
                "current_password": "testpassword123",
                "new_password": "newpassword456",
                "confirm_password": "newpassword456",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newpassword456"))
        self.assertFalse(self.user.must_change_password)

    def test_change_password_requires_matching_confirmation(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/auth/change-password/",
            {
                "current_password": "testpassword123",
                "new_password": "newpassword456",
                "confirm_password": "different789",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_requires_current_password(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/auth/change-password/",
            {
                "current_password": "wrongpassword",
                "new_password": "newpassword456",
                "confirm_password": "newpassword456",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_requires_authentication(self):
        response = self.client.post(
            "/api/auth/change-password/",
            {
                "current_password": "testpassword123",
                "new_password": "newpassword456",
                "confirm_password": "newpassword456",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_exposes_must_change_password_flag(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": "driver@example.com", "password": "testpassword123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["user"]["must_change_password"])


@override_settings(PHONE_OTP_REVEAL_CODE=True)
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PhoneOTPTests(TestCase):
    """Vérification du numéro de téléphone par code OTP (spec §14)."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="otp@example.com",
            email="otp@example.com",
            password="testpassword123",
            is_verified=True,
            phone="+221771234567",
        )

    def test_request_otp_returns_code_in_dev_and_sets_expiry(self):
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/auth/request-phone-otp/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        code = response.data["debug_code"]
        self.assertRegex(code, r"^\d{6}$")

        otp = self.user.phone_otps.latest("created_at")
        self.assertIsNotNone(otp.expires_at)
        self.assertNotEqual(otp.code_hash, code)  # jamais stocké en clair

    def test_verify_otp_marks_phone_verified(self):
        self.client.force_authenticate(self.user)
        code = self.client.post("/api/auth/request-phone-otp/", {}, format="json").data["debug_code"]
        response = self.client.post("/api/auth/verify-phone-otp/", {"code": code}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.phone_verified)
        self.assertIsNotNone(self.user.phone_verified_at)

    def test_wrong_code_consumes_attempt_then_blocks(self):
        self.client.force_authenticate(self.user)
        request_code = self.client.post("/api/auth/request-phone-otp/", {}, format="json").data["debug_code"]
        otp = self.user.phone_otps.latest("created_at")

        for _ in range(settings.PHONE_OTP_MAX_ATTEMPTS):
            response = self.client.post("/api/auth/verify-phone-otp/", {"code": "000000"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Code incorrect", str(response.data))

        # Même le bon code est refusé (compteur d'essais épuisé).
        blocked = self.client.post("/api/auth/verify-phone-otp/", {"code": request_code}, format="json")
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expired_code_is_rejected(self):
        self.client.force_authenticate(self.user)
        self.client.post("/api/auth/request-phone-otp/", {}, format="json")
        otp = self.user.phone_otps.latest("created_at")
        otp.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        otp.save(update_fields=["expires_at"])

        response = self.client.post("/api/auth/verify-phone-otp/", {"code": "123456"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expiré", str(response.data))

    def test_already_verified_account_cannot_request_new_otp(self):
        self.user.phone_verified = True
        self.user.save()
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/auth/request-phone-otp/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_prod_never_reveals_code(self):
        with override_settings(PHONE_OTP_REVEAL_CODE=False):
            self.client.force_authenticate(self.user)
            response = self.client.post("/api/auth/request-phone-otp/", {}, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertNotIn("debug_code", response.data)


class SecurityLoggingTests(TestCase):
    """Les actions sensibles laissent une trace dans le journal de sécurité (spec §16)."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="log@example.com",
            email="log@example.com",
            password="testpassword123",
            is_verified=True,
        )
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        UserRole.objects.create(user=self.user, role=Role.objects.get(name=Role.RoleName.CLIENT))

    def _log(self, action, user=None):
        from apps.security.models import SecurityLog
        return SecurityLog.objects.filter(user=user or self.user, action=action).first()

    def test_login_writes_security_log(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": "log@example.com", "password": "testpassword123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(self._log("LOGIN"))

    def test_logout_blacklists_token_and_logs(self):
        token = self.client.post(
            "/api/auth/login/",
            {"email": "log@example.com", "password": "testpassword123"},
            format="json",
        ).data["refresh"]
        self.client.force_authenticate(self.user)

        response = self.client.post("/api/auth/logout/", {"refresh": token}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(self._log("LOGOUT"))

        # Le refresh révoqué ne peut plus produire de nouvel access token.
        refresh_response = self.client.post(
            "/api/auth/token/refresh/", {"refresh": token}, format="json"
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password_writes_security_log(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/auth/change-password/",
            {
                "current_password": "testpassword123",
                "new_password": "newpassword456",
                "confirm_password": "newpassword456",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(self._log("PASSWORD_CHANGE"))
