from django.contrib import admin
from .models import PracticalTask, PracticalSession


@admin.register(PracticalTask)
class PracticalTaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "subject",
        "total_marks",
        "duration_minutes",
        "is_published",
        "is_active",
    )
    list_filter = ("subject", "is_published", "is_active")
    search_fields = ("title",)
    actions = ["publish_exam", "unpublish_exam"]

    def publish_exam(self, request, queryset):
        queryset.update(is_published=True)

    def unpublish_exam(self, request, queryset):
        queryset.update(is_published=False)


@admin.register(PracticalSession)
class PracticalSessionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "task",
        "obtained_marks",
        "percentage",
        "status",
        "start_time",
        "end_time",
    )
    list_filter = ("status", "task__subject")
    search_fields = ("user__email",)
    readonly_fields = (
        "vm_name",
        "vm_ip",
        "start_time",
        "end_time",
        "percentage",
    )
