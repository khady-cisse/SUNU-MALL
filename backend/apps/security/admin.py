from django.contrib import admin

from .models import SecurityLog


@admin.register(SecurityLog)
class SecurityLogAdmin(admin.ModelAdmin):
    list_display = ("action", "user", "ip_address", "created_at")
    list_filter = ("action",)
    date_hierarchy = "created_at"
    readonly_fields = ("user", "action", "ip_address", "user_agent", "metadata", "created_at")
    search_fields = ("user__email", "ip_address")