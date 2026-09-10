"""
Tests du support client (apps/complaints) — plaintes, tickets, workflow, PDF.

Couvre : création et isolation (un utilisateur ne voit que ses plaintes),
le workflow de traitement (assigner/commencer/escalader/répondre/résoudre/
clore/rouvrir) avec timeline immuable, l'export PDF du dossier, les tickets
support et la remontée des plaintes critiques au centre d'alertes.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework.test import APIClient

from apps.users.models import Role, UserRole

from .models import Complaint, ComplaintTimeline, SupportTicket, TicketMessage

User = get_user_model()

PDF_HEADER = b"%PDF"


class ComplaintsTestCase(TestCase):
    def setUp(self):
        Role.objects.get_or_create(name=Role.RoleName.ADMIN)
        Role.objects.get_or_create(name=Role.RoleName.ADMIN_SUPPORT)
        Role.objects.get_or_create(name=Role.RoleName.MERCHANT)
        Role.objects.get_or_create(name=Role.RoleName.CLIENT)
        self.client = APIClient()
        self.admin = self.create_user("admin@example.com", Role.RoleName.ADMIN)
        self.support = self.create_user("support@example.com", Role.RoleName.ADMIN_SUPPORT)
        self.customer = self.create_user("client@example.com", Role.RoleName.CLIENT)
        self.other_customer = self.create_user("other@example.com", Role.RoleName.CLIENT)
        self.merchant = self.create_user("merchant@example.com", Role.RoleName.MERCHANT)

    def create_user(self, email, role_name):
        user = User.objects.create_user(
            username=email, email=email, password="testpass123", is_verified=True
        )
        role = Role.objects.get(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def create_complaint(self, user, subject="Colis jamais livré", priority="high"):
        resp = self.client.post(
            "/api/complaints/complaints/",
            {
                "category": "order_not_received",
                "subject": subject,
                "description": "Première description du litige.",
                "priority": priority,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        return resp.data

    # --- création & isolation ---

    def test_customer_creates_complaint_with_reference_and_timeline(self):
        self.auth(self.customer)
        data = self.create_complaint(self.customer)
        self.assertTrue(data["reference"].startswith("PLT-"))
        self.assertEqual(data["complainant"], self.customer.id)
        self.assertEqual(data["status"], Complaint.Status.OPEN)
        self.assertEqual(len(data["timeline"]), 1)
        self.assertEqual(data["timeline"][0]["action"], ComplaintTimeline.Action.CREATED)

    def test_user_sees_only_own_complaints(self):
        self.auth(self.customer)
        self.create_complaint(self.customer)
        self.auth(self.other_customer)
        resp = self.client.get("/api/complaints/complaints/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["results"], [])

    def test_admin_sees_all_complaints(self):
        self.auth(self.customer)
        self.create_complaint(self.customer)
        self.auth(self.admin)
        resp = self.client.get("/api/complaints/complaints/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 1)

    # --- workflow de traitement ---

    def test_workflow_full_lifecycle(self):
        self.auth(self.customer)
        data = self.create_complaint(self.customer)

        self.auth(self.support)
        assigned = self.client.post(
            f"/api/complaints/complaints/{data['id']}/assign/",
            {"assignee": str(self.support.id), "note": "Prise en charge immédiate"},
            format="json",
        )
        self.assertEqual(assigned.status_code, 200, assigned.content)
        self.assertEqual(assigned.data["status"], Complaint.Status.ASSIGNED)
        self.assertEqual(assigned.data["assignee"], str(self.support.id))

        started = self.client.post(f"/api/complaints/complaints/{data['id']}/start/")
        self.assertEqual(started.data["status"], Complaint.Status.IN_PROGRESS)

        escalated = self.client.post(
            f"/api/complaints/complaints/{data['id']}/escalate/",
            {"note": "Nécessite validation finance"},
            format="json",
        )
        self.assertEqual(escalated.data["status"], Complaint.Status.ESCALATED)

        resolved = self.client.post(
            f"/api/complaints/complaints/{data['id']}/resolve/",
            {"decision": "refund", "resolution_note": "Remboursement intégral accordé"},
            format="json",
        )
        self.assertEqual(resolved.status_code, 200, resolved.content)
        self.assertEqual(resolved.data["status"], Complaint.Status.RESOLVED)
        self.assertEqual(resolved.data["resolution_decision"], "refund")
        self.assertIsNotNone(resolved.data["resolved_at"])

        closed = self.client.post(f"/api/complaints/complaints/{data['id']}/close/")
        self.assertEqual(closed.data["status"], Complaint.Status.CLOSED)

        reopened = self.client.post(f"/api/complaints/complaints/{data['id']}/reopen/")
        self.assertEqual(reopened.data["status"], Complaint.Status.OPEN)

        complaint = Complaint.objects.get(pk=data["id"])
        actions = [entry.action for entry in complaint.timeline.all()]
        self.assertEqual(actions, [
            ComplaintTimeline.Action.CREATED,
            ComplaintTimeline.Action.ASSIGNED,
            ComplaintTimeline.Action.STARTED,
            ComplaintTimeline.Action.ESCALATED,
            ComplaintTimeline.Action.RESOLVED,
            ComplaintTimeline.Action.CLOSED,
            ComplaintTimeline.Action.REOPENED,
        ])

    def test_resolve_requires_decision(self):
        self.auth(self.customer)
        data = self.create_complaint(self.customer)
        self.auth(self.support)
        resp = self.client.post(
            f"/api/complaints/complaints/{data['id']}/resolve/",
            {"resolution_note": "Sans décision"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_workflow_actions_require_support_permission(self):
        self.auth(self.customer)
        data = self.create_complaint(self.customer)
        resp = self.client.post(f"/api/complaints/complaints/{data['id']}/resolve/",
                                {"decision": "info"}, format="json")
        self.assertEqual(resp.status_code, 403)

    # --- timeline immuable ---

    def test_timeline_is_immutable(self):
        self.auth(self.customer)
        data = self.create_complaint(self.customer)
        complaint = Complaint.objects.get(pk=data["id"])
        entry = complaint.timeline.first()
        with self.assertRaises(NotImplementedError):
            entry.delete()

    # --- pièces jointes + PDF ---

    def test_add_attachment(self):
        self.auth(self.customer)
        data = self.create_complaint(self.customer)
        self.auth(self.support)
        resp = self.client.post(
            f"/api/complaints/complaints/{data['id']}/add_attachment/",
            {
                "filename": "preuve-commande.png",
                "content_type": "image/png",
                "size_bytes": 2048,
                "storage_key": "complaints/original-id/preuve-commande.png",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["filename"], "preuve-commande.png")

    def test_export_pdf_dossier(self):
        self.auth(self.customer)
        data = self.create_complaint(self.customer)
        self.auth(self.support)
        resp = self.client.get(f"/api/complaints/complaints/{data['id']}/pdf/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(PDF_HEADER))
        self.assertIn(f"dossier-{data['reference']}.pdf".encode(), resp["Content-Disposition"].encode())
        # Le dossier contient la référence et le début de l'historique.
        self.assertIn(data["reference"].encode(), resp.content)

    # --- tickets de support ---

    def test_ticket_create_and_support_reply(self):
        self.auth(self.merchant)
        created = self.client.post(
            "/api/complaints/tickets/",
            {"category": "payment", "subject": "Retard de retrait", "description": "Mon retrait est en attente."},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertTrue(created.data["reference"].startswith("TKT-"))
        self.assertEqual(created.data["status"], SupportTicket.Status.NEW)

        self.auth(self.support)
        reply = self.client.post(
            f"/api/complaints/tickets/{created.data['id']}/reply/",
            {"body": "Votre retrait sera libéré sous 48h."},
            format="json",
        )
        self.assertEqual(reply.status_code, 201, reply.content)
        self.assertTrue(reply.data["is_support_reply"])

        resolved = self.client.post(f"/api/complaints/tickets/{created.data['id']}/resolve/")
        self.assertEqual(resolved.data["status"], SupportTicket.Status.RESOLVED)

    def test_ticket_isolation(self):
        self.auth(self.merchant)
        created = self.client.post(
            "/api/complaints/tickets/",
            {"category": "help", "subject": "Aide configuration", "description": "Comment créer une boutique ?"},
            format="json",
        ).data
        self.auth(self.customer)
        resp = self.client.get("/api/complaints/tickets/")
        self.assertEqual(resp.data["results"], [])

    def test_ticket_resolve_requires_support(self):
        self.auth(self.merchant)
        created = self.client.post(
            "/api/complaints/tickets/",
            {"category": "help", "subject": "Aide", "description": "Question"},
            format="json",
        ).data
        resp = self.client.post(f"/api/complaints/tickets/{created['id']}/resolve/")
        self.assertEqual(resp.status_code, 403)

    # --- remontée au centre d'alertes (apps/ops) ---

    def test_critical_complaint_reaches_alert_center(self):
        from apps.ops.services import alert_center

        Complaint.objects.create(
            complainant=self.customer, category="defective_product",
            subject="Produit dangereux", priority=Complaint.Priority.CRITICAL,
        )
        alerts = alert_center()
        codes = {a["code"] for a in alerts}
        self.assertIn("complaints_critical", codes)
        self.assertEqual(
            next(a for a in alerts if a["code"] == "complaints_critical")["count"], 1
        )