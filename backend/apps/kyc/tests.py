"""
Tests du module KYC — vendeurs et livreurs restent STRICTEMENT séparés.

Spec §22 : 10 tests obligatoires
1. Dépôt vendeur : 201 + pièces dans `kyc/sellers/seller_{user_id}/{kyc_id}/`
2. Dépôt livreur : 201 + pièces dans `kyc/drivers/driver_{user_id}/{kyc_id}/`
3. Client : 403 au dépôt vendeur
4. Croisé : un LIVREUR ne peut pas déposer un dossier vendeur (403)
5. Croisé : un VENDEUR ne peut pas déposer un dossier livreur (403)
6. IDs fournis au payload : totalement ignorés → le propriétaire reste
   `request.user`, jamais ce qui est envoyé
7. Séparation admin : les listes "vendeurs" et "livreurs" sont distinctes
8. Immuabilité : le propriétaire d'un dossier ne change JAMAIS
9. Approbation admin : VERIFIED + notification + trace d'audit
10. Rejet admin : REJECTED + motif + notification + trace d'audit

Ensuite : les gating (§21) boutique/livraison et l'accès aux pièces.
"""
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.catalog.models import StoreCategory
from apps.kyc.models import DriverKYC, KYCAuditLog, SellerKYC
from apps.monetization.models import Notification
from apps.users.models import Role, User

KYC_FS = override_settings(KYC_STORAGE_BACKEND="fs")


def make_user(email, role_name):
    user = User.objects.create_user(
        username=email.split("@")[0],
        email=email,
        password="TestPass123!",
        first_name="Aminata",
        last_name="Diallo",
    )
    role = Role.objects.get_or_create(name=role_name)[0]
    user.user_roles.create(role=role)
    return user


def cni_upload(name="front.jpg"):
    return SimpleUploadedFile(name, b"\xff\xd8\xff\xe0" + b"0123456789" * 256, content_type="image/jpeg")


@KYC_FS
class KYCSubmitTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override_storage = override_settings(KYC_STORAGE_LOCATION=self.tmp)
        self.override_storage.enable()
        self.addCleanup(self.override_storage.disable)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.merchant = make_user("merchant@sunu.test", Role.RoleName.MERCHANT)
        self.driver = make_user("driver@sunu.test", Role.RoleName.DRIVER)
        self.client_user = make_user("client@sunu.test", Role.RoleName.CLIENT)
        self.admin = make_user("admin@sunu.test", Role.RoleName.ADMIN)

        self.client = APIClient()

    def _submit(self, path, user, **extra):
        self.client.force_authenticate(user)
        payload = {
            "document_type": "cni",
            "document_front": cni_upload("front.jpg"),
            "document_back": cni_upload("back.jpg"),
            **extra,
        }
        return self.client.post(path, payload, format="multipart")

    # --- 1 & 2 : dépôt et séparation des chemins MinIO ---

    def test_seller_submit_201_and_private_path(self):
        response = self._submit("/api/kyc/seller-kyc/submit/", self.merchant)
        self.assertEqual(response.status_code, 201, response.data)

        kyc = SellerKYC.objects.get(seller=self.merchant)
        self.assertEqual(kyc.status, SellerKYC.Status.PENDING)
        self.assertIn(f"kyc/sellers/seller_{self.merchant.id}/{kyc.id}/", kyc.document_front)
        self.assertIn(f"kyc/sellers/seller_{self.merchant.id}/{kyc.id}/", kyc.document_back)
        self.assertTrue(kyc.document_front.endswith("front.jpg"))
        self.assertTrue(kyc.document_back.endswith("back.jpg"))

    def test_seller_resubmission_is_200(self):
        self._submit("/api/kyc/seller-kyc/submit/", self.merchant)
        second = self._submit("/api/kyc/seller-kyc/submit/", self.merchant)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(SellerKYC.objects.filter(seller=self.merchant).count(), 1)

    def test_driver_submit_201_and_private_path(self):
        response = self._submit("/api/kyc/driver-kyc/submit/", self.driver)
        self.assertEqual(response.status_code, 201, response.data)

        kyc = DriverKYC.objects.get(driver=self.driver)
        self.assertIn(f"kyc/drivers/driver_{self.driver.id}/{kyc.id}/", kyc.document_front)
        self.assertIn(f"kyc/drivers/driver_{self.driver.id}/{kyc.id}/", kyc.document_back)

    # --- 3, 4 & 5 : rôles et croisements ---

    def test_client_cannot_submit_seller_kyc(self):
        response = self._submit("/api/kyc/seller-kyc/submit/", self.client_user)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(SellerKYC.objects.count(), 0)

    def test_driver_cannot_submit_seller_kyc(self):
        response = self._submit("/api/kyc/seller-kyc/submit/", self.driver)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(SellerKYC.objects.count(), 0)

    def test_merchant_cannot_submit_driver_kyc(self):
        response = self._submit("/api/kyc/driver-kyc/submit/", self.merchant)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(DriverKYC.objects.count(), 0)

    # --- 6 : le propriétaire vient du compte connecté, jamais du payload ---

    def test_payload_owner_fields_are_rejected(self):
        self.client.force_authenticate(self.merchant)
        response = self.client.post(
            "/api/kyc/seller-kyc/submit/",
            {
                "document_type": "cni",
                "document_front": cni_upload("front.jpg"),
                "document_back": cni_upload("back.jpg"),
                "seller_id": str(self.driver.id),  # tentative de vol/erreur
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(SellerKYC.objects.count(), 0)

    def test_submitted_owner_is_always_request_user(self):
        self._submit("/api/kyc/seller-kyc/submit/", self.merchant)
        kyc = SellerKYC.objects.get()
        self.assertEqual(kyc.seller_id, self.merchant.id)
        self.assertNotEqual(kyc.seller_id, self.driver.id)

    def test_me_returns_own_dossier_or_404(self):
        self.client.force_authenticate(self.merchant)
        response = self.client.get("/api/kyc/seller-kyc/me/")
        self.assertEqual(response.status_code, 404)
        self._submit("/api/kyc/seller-kyc/submit/", self.merchant)
        response = self.client.get("/api/kyc/seller-kyc/me/")
        self.assertEqual(response.status_code, 200)

    # --- 7 : listes admin strictement séparées par type ---

    def test_admin_lists_are_separated_by_type(self):
        seller_kyc = SellerKYC.objects.create(
            seller=self.merchant,
            document_type="cni", document_front="kyc/sellers/1/f.jpg", document_back="kyc/sellers/1/b.jpg",
        )
        driver_kyc = DriverKYC.objects.create(
            driver=self.driver,
            document_type="cni", document_front="kyc/drivers/1/f.jpg", document_back="kyc/drivers/1/b.jpg",
        )
        self.client.force_authenticate(self.admin)

        sellers = self.client.get("/api/kyc/seller-kyc/")
        self.assertEqual(sellers.status_code, 200)
        self.assertEqual(sellers.data["count"], 1)
        self.assertEqual(sellers.data["results"][0]["id"], str(seller_kyc.id))
        self.assertTrue(all("driver" not in r for r in sellers.data["results"]))

        drivers = self.client.get("/api/kyc/driver-kyc/")
        self.assertEqual(drivers.status_code, 200)
        self.assertEqual(drivers.data["count"], 1)
        self.assertEqual(drivers.data["results"][0]["id"], str(driver_kyc.id))

    def test_admin_only_can_list_kyc(self):
        self.client.force_authenticate(self.merchant)
        self.assertEqual(self.client.get("/api/kyc/seller-kyc/").status_code, 403)
        self.client.force_authenticate(self.driver)
        self.assertEqual(self.client.get("/api/kyc/driver-kyc/").status_code, 403)

    # --- 8 : immuabilité de l'association ---

    def test_no_update_endpoint_exists(self):
        seller_kyc = SellerKYC.objects.create(
            seller=self.merchant,
            document_type="cni", document_front="kyc/sellers/1/f.jpg", document_back="kyc/sellers/1/b.jpg",
        )
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.put(f"/api/kyc/seller-kyc/{seller_kyc.id}/", {"seller": self.driver.id}).status_code, 405)
        self.assertEqual(self.client.patch(f"/api/kyc/seller-kyc/{seller_kyc.id}/", {"seller": self.driver.id}).status_code, 405)
        seller_kyc.refresh_from_db()
        self.assertEqual(seller_kyc.seller_id, self.merchant.id)

    def test_owner_role_mismatch_blocks_admin_actions(self):
        seller_kyc = SellerKYC.objects.create(
            seller=self.merchant,
            document_type="cni", document_front="kyc/sellers/1/f.jpg", document_back="kyc/sellers/1/b.jpg",
        )
        # On retire le rôle "merchant" au propriétaire : le dossier devient
        # incohérent (un vendeur "démuselé" n'est plus un vendeur) et toute
        # action admin doit être bloquée.
        self.merchant.user_roles.all().delete()
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f"/api/kyc/seller-kyc/{seller_kyc.id}/approve/").status_code, 400)
        self.assertEqual(self.client.post(f"/api/kyc/seller-kyc/{seller_kyc.id}/reject/", {"reason": "x"}).status_code, 400)

    # --- 9 & 10 : approbation / rejet admin ---

    def test_admin_approve_verified_notification_and_audit(self):
        kyc = SellerKYC.objects.create(
            seller=self.merchant,
            document_type="cni", document_front="kyc/sellers/1/f.jpg", document_back="kyc/sellers/1/b.jpg",
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/kyc/seller-kyc/{kyc.id}/approve/")
        self.assertEqual(response.status_code, 200, response.data)
        kyc.refresh_from_db()
        self.assertEqual(kyc.status, SellerKYC.Status.VERIFIED)
        self.assertIsNotNone(kyc.verified_at)

        self.assertTrue(
            Notification.objects.filter(user=self.merchant, subject__contains="vérifiée", status=Notification.Status.SENT).exists()
        )
        self.assertTrue(
            KYCAuditLog.objects.filter(action=KYCAuditLog.Action.ADMIN_APPROVE_SELLER_KYC, admin=self.admin, kyc_id=str(kyc.id)).exists()
        )

    def test_admin_reject_with_reason_notification_and_audit(self):
        kyc = DriverKYC.objects.create(
            driver=self.driver,
            document_type="cni", document_front="kyc/drivers/1/f.jpg", document_back="kyc/drivers/1/b.jpg",
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/kyc/driver-kyc/{kyc.id}/reject/", {"reason": "Photo floue"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        kyc.refresh_from_db()
        self.assertEqual(kyc.status, DriverKYC.Status.REJECTED)
        self.assertEqual(kyc.rejection_reason, "Photo floue")

        notification = Notification.objects.filter(user=self.driver).first()
        self.assertIsNotNone(notification)
        self.assertIn("Photo floue", notification.message)
        self.assertTrue(
            KYCAuditLog.objects.filter(action=KYCAuditLog.Action.ADMIN_REJECT_DRIVER_KYC, admin=self.admin, kyc_id=str(kyc.id)).exists()
        )

    def test_view_logs_audit(self):
        kyc = SellerKYC.objects.create(
            seller=self.merchant,
            document_type="cni", document_front="kyc/sellers/1/f.jpg", document_back="kyc/sellers/1/b.jpg",
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get(f"/api/kyc/seller-kyc/{kyc.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["document_front"], "kyc/sellers/1/f.jpg")
        self.assertTrue(
            KYCAuditLog.objects.filter(action=KYCAuditLog.Action.ADMIN_VIEW_SELLER_KYC, admin=self.admin).exists()
        )

    def test_driver_cannot_access_seller_documents(self):
        kyc = SellerKYC.objects.create(
            seller=self.merchant,
            document_type="cni", document_front="kyc/sellers/1/f.jpg", document_back="kyc/sellers/1/b.jpg",
        )
        self.client.force_authenticate(self.driver)
        self.assertEqual(self.client.get(f"/api/kyc/seller-kyc/{kyc.id}/").status_code, 403)


@KYC_FS
class KYCGatingTests(TestCase):
    """Section 21 : sans KYC vérifié, pas de boutique ouverte, pas de course acceptée."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override_storage = override_settings(KYC_STORAGE_LOCATION=self.tmp)
        self.override_storage.enable()
        self.addCleanup(self.override_storage.disable)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.merchant = make_user("m@sunu.test", Role.RoleName.MERCHANT)
        self.driver = make_user("d@sunu.test", Role.RoleName.DRIVER)
        self.client = APIClient()

    def _verify_seller(self):
        return SellerKYC.objects.create(
            seller=self.merchant, document_type="cni",
            document_front="kyc/sellers/1/f.jpg", document_back="kyc/sellers/1/b.jpg",
            status=SellerKYC.Status.VERIFIED, submitted_at=None,
        )

    def _verify_driver(self):
        return DriverKYC.objects.create(
            driver=self.driver, document_type="cni",
            document_front="kyc/drivers/1/f.jpg", document_back="kyc/drivers/1/b.jpg",
            status=DriverKYC.Status.VERIFIED, submitted_at=None,
        )

    def test_merchant_cannot_create_store_without_verified_kyc(self):
        self.client.force_authenticate(self.merchant)
        response = self.client.post("/api/catalog/stores/", {"name": "Boutique test"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_merchant_can_create_store_with_verified_kyc(self):
        self._verify_seller()
        self.client.force_authenticate(self.merchant)
        category = StoreCategory.objects.create(name="Alimentation")
        response = self.client.post(
            "/api/catalog/stores/", {"name": "Boutique test", "category": category.id}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_driver_cannot_go_available_without_verified_kyc(self):
        self.client.force_authenticate(self.driver)
        response = self.client.patch("/api/orders/drivers/me/", {"availability_status": "available"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_driver_can_go_offline_without_verified_kyc(self):
        self.client.force_authenticate(self.driver)
        response = self.client.patch("/api/orders/drivers/me/", {"availability_status": "offline"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def test_driver_can_go_available_with_verified_kyc(self):
        self._verify_driver()
        self.client.force_authenticate(self.driver)
        response = self.client.patch("/api/orders/drivers/me/", {"availability_status": "available"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["availability_status"], "available")