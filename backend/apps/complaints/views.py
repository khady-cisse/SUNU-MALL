"""
Vues du support client : plaintes (workflow + export PDF) et tickets.

Permissions :
- un utilisateur crée ses propres plaintes ; un admin (support) voit tout ;
- les actions de traitement (assigner / commencer / escalader / répondre /
  résoudre / clore / rouvrir) exigent `complaints.*` ;
- les tickets sont accessibles à leur requérant et au support.
"""
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.security.utils import log_admin_event
from apps.users.permissions import HasPermission

from .models import Complaint, ComplaintAttachment, ComplaintTimeline, SupportTicket, TicketMessage
from .pdf import complaint_dossier_pdf
from .serializers import (
    ComplaintCreateSerializer, ComplaintSerializer, SupportTicketSerializer, TicketMessageSerializer,
)


class HasComplaintsView(HasPermission):
    required_permission = "complaints.view"


class HasComplaintsManage(HasPermission):
    required_permission = "complaints.manage"


class ComplaintViewSet(viewsets.ModelViewSet):
    """Plaintes : lecture par leur émetteur, tout par le support admin."""
    serializer_class = ComplaintSerializer
    queryset = Complaint.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        if self.action in ["assign", "start", "escalate", "respond", "resolve",
                           "close", "reopen", "add_attachment"]:
            return [permissions.IsAuthenticated(), HasComplaintsManage()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == "create":
            return ComplaintCreateSerializer
        return ComplaintSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "complainant", "assignee", "store", "order", "delivery"
        ).prefetch_related("timeline", "attachments")
        user = self.request.user
        if user.is_admin():
            qs = self._apply_filters(qs)
        else:
            qs = qs.filter(complainant=user)
        return qs

    def _apply_filters(self, qs):
        """Filtres du centre admin : statut, priorité, période, recherche."""
        params = self.request.query_params
        status_ = params.get("status")
        priority = params.get("priority")
        date_from = params.get("created_from")
        date_to = params.get("created_to")
        search = params.get("search")
        if status_:
            qs = qs.filter(status=status_)
        if priority:
            qs = qs.filter(priority=priority)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if search:
            qs = qs.filter(
                Q(reference__icontains=search)
                | Q(subject__icontains=search)
                | Q(complainant__email__icontains=search)
            )
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        complaint = serializer.save(complainant=self.request.user)
        complaint.append_timeline(self.request.user, ComplaintTimeline.Action.CREATED,
                                  note="Plainte déposée par l'utilisateur")
        return Response(ComplaintSerializer(complaint).data,
                        status=status.HTTP_201_CREATED)

    # --- Workflow de traitement (actions validées en permissions) ---

    def _transition(self, request, pk, target_status, action_code, note="", extra_save=None):
        complaint = self.get_object()
        complaint.status = target_status
        if extra_save:
            extra_save(complaint)
        complaint.save()
        complaint.append_timeline(request.user, action_code, note=note)
        return Response(self.get_serializer(complaint).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """Assigne la plainte à un administrateur du support."""
        return self._transition(
            request, pk, Complaint.Status.ASSIGNED, ComplaintTimeline.Action.ASSIGNED,
            note=request.data.get("note", ""),
            extra_save=lambda c: setattr(c, "assignee_id", request.data.get("assignee") or c.assignee_id),
        )

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Démarre le traitement (assignée → en cours)."""
        return self._transition(
            request, pk, Complaint.Status.IN_PROGRESS, ComplaintTimeline.Action.STARTED,
            note=request.data.get("note", ""),
        )

    @action(detail=True, methods=["post"])
    def escalate(self, request, pk=None):
        """Escale une plainte bloquée (remonte au niveau supérieur)."""
        return self._transition(
            request, pk, Complaint.Status.ESCALATED, ComplaintTimeline.Action.ESCALATED,
            note=request.data.get("note", "Escale"),
        )

    @action(detail=True, methods=["post"])
    def respond(self, request, pk=None):
        """Réponse apportée au plaignant (laisse la plainte en cours)."""
        return self._transition(
            request, pk, Complaint.Status.IN_PROGRESS, ComplaintTimeline.Action.RESPONDED,
            note=request.data.get("note", ""),
        )

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """Résout : exige une décision (remboursement, échange, retour...)."""
        decision = request.data.get("decision", "")
        if decision not in Complaint.Decision.values:
            raise ValidationError("Champ 'decision' requis (refund, exchange, return, compensation, info, no_action).")
        complaint = self.get_object()
        complaint.status = Complaint.Status.RESOLVED
        complaint.resolution_decision = decision
        complaint.resolution_note = request.data.get("resolution_note", "")
        complaint.resolved_at = timezone.now()
        complaint.save()
        complaint.append_timeline(request.user, ComplaintTimeline.Action.RESOLVED,
                                  note="Décision : " + complaint.get_resolution_decision_display())
        log_admin_event(request.user, "resolve", request, object_type="Complaint",
                        object_id=complaint.reference, summary=f"Plainte résolue : {complaint.reference}")
        return Response(self.get_serializer(complaint).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        complaint = self.get_object()
        complaint.status = Complaint.Status.CLOSED
        complaint.closed_at = timezone.now()
        complaint.save()
        complaint.append_timeline(request.user, ComplaintTimeline.Action.CLOSED, note=request.data.get("note", ""))
        return Response(self.get_serializer(complaint).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        complaint = self.get_object()
        complaint.status = Complaint.Status.OPEN
        complaint.resolved_at = None
        complaint.closed_at = None
        complaint.save()
        complaint.append_timeline(request.user, ComplaintTimeline.Action.REOPENED, note=request.data.get("note", ""))
        return Response(self.get_serializer(complaint).data)

    @action(detail=True, methods=["post"])
    def add_attachment(self, request, pk=None):
        complaint = self.get_object()
        attachment = ComplaintAttachment.objects.create(
            complaint=complaint,
            filename=request.data.get("filename", "piece-jointe"),
            content_type=request.data.get("content_type", ""),
            size_bytes=int(request.data.get("size_bytes", 0) or 0),
            storage_key=request.data.get("storage_key", ""),
            uploaded_by=request.user,
        )
        return Response({"id": str(attachment.id), "filename": attachment.filename},
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="pdf")
    def export_pdf(self, request, pk=None):
        """Dossier PDF de la plainte (historique complet)."""
        complaint = self.get_object()
        timeline = complaint.timeline.select_related("actor").all()
        attachments = complaint.attachments.all()
        pdf_bytes = complaint_dossier_pdf(complaint, timeline, attachments)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="dossier-{complaint.reference}.pdf"'
        return response


class SupportTicketViewSet(viewsets.ModelViewSet):
    """Tickets de support : requérant ou support."""
    serializer_class = SupportTicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return SupportTicketSerializer

    def get_queryset(self):
        qs = SupportTicket.objects.select_related("requester", "assigned_to").prefetch_related("messages")
        user = self.request.user
        if user.is_admin():
            return qs
        return qs.filter(requester=user)

    def perform_create(self, serializer):
        serializer.save(requester=self.request.user)

    @action(detail=True, methods=["post"])
    def reply(self, request, pk=None):
        """Réponse (requérant ou support) — une réponse support archive l'état."""

        ticket = self.get_object()
        body = request.data.get("body", "").strip()
        if not body:
            raise ValidationError("Champ 'body' requis.")
        is_support = request.user.is_admin()
        TicketMessage.objects.create(
            ticket=ticket, author=request.user, body=body, is_support_reply=is_support,
        )
        if is_support:
            if ticket.status in [SupportTicket.Status.NEW, SupportTicket.Status.OPEN]:
                ticket.status = SupportTicket.Status.ANSWERED
        else:
            ticket.status = SupportTicket.Status.OPEN
        ticket.save()
        return Response(TicketMessageSerializer(ticket.messages.last()).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        if not request.user.is_admin():
            self.permission_denied(request, message="Seul le support peut résoudre un ticket.")
        ticket = self.get_object()
        ticket.status = SupportTicket.Status.RESOLVED
        ticket.save()
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        ticket = self.get_object()
        if not request.user.is_admin() and ticket.requester_id != request.user.id:
            self.permission_denied(request, message="Seul le support ou le requérant peut clore ce ticket.")
        ticket.status = SupportTicket.Status.CLOSED
        ticket.save()
        return Response(self.get_serializer(ticket).data)