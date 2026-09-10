"""Serialiseurs des plaintes et tickets support (apps/complaints)."""
from rest_framework import serializers

from .models import Complaint, ComplaintAttachment, ComplaintTimeline, SupportTicket, TicketMessage


class ComplaintTimelineSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = ComplaintTimeline
        fields = ["id", "action", "note", "metadata", "actor_name", "created_at"]
        read_only_fields = fields

    def get_actor_name(self, obj):
        if not obj.actor:
            return "Système"
        return obj.actor.get_full_name() or obj.actor.email


class ComplaintAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ComplaintAttachment
        fields = ["id", "filename", "content_type", "size_bytes", "storage_key", "uploaded_by_name", "created_at"]
        read_only_fields = ["id", "uploaded_by_name", "created_at"]

    def get_uploaded_by_name(self, obj):
        if not obj.uploaded_by:
            return ""
        return obj.uploaded_by.get_full_name() or obj.uploaded_by.email


class ComplaintSerializer(serializers.ModelSerializer):
    complainant_name = serializers.SerializerMethodField()
    assignee_name = serializers.SerializerMethodField()
    order_reference = serializers.CharField(source="order.id", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    timeline = ComplaintTimelineSerializer(many=True, read_only=True)
    attachments = ComplaintAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Complaint
        fields = [
            "id", "reference", "complainant", "complainant_name", "order", "order_reference",
            "store", "store_name", "delivery", "driver", "payment",
            "category", "subject", "description", "priority", "status",
            "assignee", "assignee_name", "resolution_decision", "resolution_note",
            "resolved_at", "closed_at", "timeline", "attachments", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "reference", "complainant", "status", "resolved_at",
                            "closed_at", "timeline", "attachments", "created_at", "updated_at"]

    def get_complainant_name(self, obj):
        return obj.complainant.get_full_name() or obj.complainant.email

    def get_assignee_name(self, obj):
        if not obj.assignee:
            return ""
        return obj.assignee.get_full_name() or obj.assignee.email


class ComplaintCreateSerializer(serializers.ModelSerializer):
    """Création par un utilisateur connecté (complainant imposé côté backend)."""

    class Meta:
        model = Complaint
        fields = [
            "order", "store", "delivery", "driver", "payment",
            "category", "subject", "description", "priority",
        ]


class TicketMessageSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = TicketMessage
        fields = ["id", "author", "author_name", "body", "is_support_reply", "created_at"]
        read_only_fields = ["id", "author", "author_name", "is_support_reply", "created_at"]

    def get_author_name(self, obj):
        if not obj.author:
            return ""
        return obj.author.get_full_name() or obj.author.email


class SupportTicketSerializer(serializers.ModelSerializer):
    requester_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    # Fil de discussion (réponses requérant + support), exposé pour les pages
    # « Mes tickets » des utilisateurs et la page admin.
    messages = TicketMessageSerializer(many=True, read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            "id", "reference", "requester", "requester_name", "category", "subject",
            "description", "status", "assigned_to", "assigned_to_name", "messages",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "reference", "requester", "status", "created_at", "updated_at"]

    def get_requester_name(self, obj):
        return obj.requester.get_full_name() or obj.requester.email

    def get_assigned_to_name(self, obj):
        if not obj.assigned_to:
            return ""
        return obj.assigned_to.get_full_name() or obj.assigned_to.email