from django.contrib import admin

from .models import Complaint, ComplaintAttachment, ComplaintTimeline, SupportTicket, TicketMessage


class ComplaintTimelineInline(admin.TabularInline):
    model = ComplaintTimeline
    extra = 0
    can_delete = False


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ["reference", "subject", "category", "priority", "status", "assignee", "created_at"]
    list_filter = ["category", "priority", "status"]
    search_fields = ["reference", "subject", "complainant__email"]
    inlines = [ComplaintTimelineInline]


@admin.register(ComplaintAttachment)
class ComplaintAttachmentAdmin(admin.ModelAdmin):
    list_display = ["filename", "complaint", "size_bytes", "created_at"]
    search_fields = ["filename"]


@admin.register(ComplaintTimeline)
class ComplaintTimelineAdmin(admin.ModelAdmin):
    list_display = ["complaint", "action", "actor", "created_at"]
    list_filter = ["action"]
    readonly_fields = ["complaint", "actor", "action", "note", "metadata", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ["reference", "subject", "category", "status", "assigned_to", "created_at"]
    list_filter = ["category", "status"]
    search_fields = ["reference", "subject", "requester__email"]


@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ["ticket", "author", "is_support_reply", "created_at"]
    list_filter = ["is_support_reply"]