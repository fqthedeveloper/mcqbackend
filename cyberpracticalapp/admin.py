from django.contrib import admin
from .models import (
    CyberMachineTemplate,
    CyberTopology,
    CyberPracticalTask,
    CyberSession,
    CyberMachineSession,
)


# =========================================================
# MACHINE TEMPLATE ADMIN
# =========================================================

@admin.register(CyberMachineTemplate)
class CyberMachineTemplateAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'name',
        'role',
        'base_box',
        'memory_mb',
        'cpu_count',
        'gui_enabled',
        'is_active',
        'created_at',
    )

    list_filter = (
        'role',
        'gui_enabled',
        'is_active',
    )

    search_fields = (
        'name',
        'base_box',
    )

    readonly_fields = (
        'created_at',
    )

    ordering = (
        '-id',
    )


# =========================================================
# TOPOLOGY ADMIN
# =========================================================

@admin.register(CyberTopology)
class CyberTopologyAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'name',
        'network_name',
        'attacker_template',
        'victim_template',
        'monitor_template',
        'is_active',
        'created_at',
    )

    list_filter = (
        'is_active',
    )

    search_fields = (
        'name',
        'network_name',
    )

    readonly_fields = (
        'created_at',
    )

    ordering = (
        '-id',
    )


# =========================================================
# PRACTICAL TASK ADMIN
# =========================================================

@admin.register(CyberPracticalTask)
class CyberPracticalTaskAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'title',
        'subject',
        'topology',
        'difficulty',
        'duration_minutes',
        'total_marks',
        'is_published',
        'is_active',
        'created_at',
    )

    list_filter = (
        'difficulty',
        'is_published',
        'is_active',
        'subject',
    )

    search_fields = (
        'title',
    )

    readonly_fields = (
        'created_at',
    )

    ordering = (
        '-id',
    )

    fieldsets = (

        (
            'Basic Information',
            {
                'fields': (
                    'title',
                    'description',
                    'subject',
                    'topology',
                    'difficulty',
                )
            }
        ),

        (
            'Exam Configuration',
            {
                'fields': (
                    'duration_minutes',
                    'total_marks',
                    'variable_schema',
                )
            }
        ),

        (
            'Attacker Machine',
            {
                'fields': (
                    'attacker_init_template',
                )
            }
        ),

        (
            'Victim Machine',
            {
                'fields': (
                    'victim_init_template',
                )
            }
        ),

        (
            'Monitor Machine',
            {
                'fields': (
                    'monitor_init_template',
                )
            }
        ),

        (
            'Verification',
            {
                'fields': (
                    'verify_template',
                )
            }
        ),

        (
            'Publishing',
            {
                'fields': (
                    'is_published',
                    'is_active',
                )
            }
        ),

        (
            'Metadata',
            {
                'fields': (
                    'created_at',
                )
            }
        ),
    )


# =========================================================
# MACHINE SESSION INLINE
# =========================================================

class CyberMachineSessionInline(admin.TabularInline):

    model = CyberMachineSession

    extra = 0

    can_delete = False

    readonly_fields = (
        'role',
        'template',
        'vm_name',
        'vm_ip',
        'guacamole_connection_id',
        'guacamole_url',
        'generated_username',
        'generated_password',
        'status',
        'recording_path',
        'created_at',
    )

    show_change_link = True


# =========================================================
# CYBER SESSION ADMIN
# =========================================================

@admin.register(CyberSession)
class CyberSessionAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'user',
        'task',
        'status',
        'obtained_marks',
        'percentage',
        'is_passed',
        'start_time',
        'end_time',
    )

    list_filter = (
        'status',
        'is_passed',
        'task',
    )

    search_fields = (
        'user__generated_username',
        'task__title',
    )

    readonly_fields = (
        'variables',
        'verification_output',
        'verification_details',
        'history_path',
        'start_time',
        'end_time',
        'created_at',
    )

    ordering = (
        '-id',
    )

    inlines = [
        CyberMachineSessionInline
    ]

    fieldsets = (

        (
            'Session Information',
            {
                'fields': (
                    'user',
                    'task',
                    'status',
                )
            }
        ),

        (
            'Generated Variables',
            {
                'fields': (
                    'variables',
                )
            }
        ),

        (
            'Result',
            {
                'fields': (
                    'obtained_marks',
                    'percentage',
                    'is_passed',
                )
            }
        ),

        (
            'Verification',
            {
                'fields': (
                    'verification_output',
                    'verification_details',
                )
            }
        ),

        (
            'History / Replay',
            {
                'fields': (
                    'history_path',
                )
            }
        ),

        (
            'Timing',
            {
                'fields': (
                    'start_time',
                    'end_time',
                    'created_at',
                )
            }
        ),
    )


# =========================================================
# MACHINE SESSION ADMIN
# =========================================================

@admin.register(CyberMachineSession)
class CyberMachineSessionAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'session',
        'role',
        'vm_name',
        'vm_ip',
        'status',
        'generated_username',
        'created_at',
    )

    list_filter = (
        'role',
        'status',
    )

    search_fields = (
        'vm_name',
        'vm_ip',
        'generated_username',
    )

    readonly_fields = (
        'created_at',
    )

    ordering = (
        '-id',
    )

    fieldsets = (

        (
            'Machine Information',
            {
                'fields': (
                    'session',
                    'role',
                    'template',
                    'status',
                )
            }
        ),

        (
            'VM Details',
            {
                'fields': (
                    'vm_name',
                    'vm_ip',
                    'generated_username',
                    'generated_password',
                )
            }
        ),

        (
            'Guacamole',
            {
                'fields': (
                    'guacamole_connection_id',
                    'guacamole_url',
                )
            }
        ),

        (
            'Recording',
            {
                'fields': (
                    'recording_path',
                )
            }
        ),

        (
            'Metadata',
            {
                'fields': (
                    'created_at',
                )
            }
        ),
    )