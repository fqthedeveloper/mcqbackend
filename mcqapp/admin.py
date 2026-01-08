from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import *


class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'username', 'user_type', 'is_active')
    ordering = ('email',)
    search_fields = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('User Type', {'fields': ('user_type',)}),
        ('Force Password Change', {'fields': ('force_password_change',)}),
        ('Permissions', {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions'
            )
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'user_type', 'password1', 'password2'),
        }),
    )

    filter_horizontal = ('groups', 'user_permissions')


class StudentSubjectEnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'is_active')
    list_filter = ('is_active', 'subject')


class QuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'subject', 'marks')
    list_filter = ('subject',)


class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'mode', 'is_published')
    list_filter = ('subject', 'mode')


class ExamSessionAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'is_completed')


class ResultAdmin(admin.ModelAdmin):
    list_display = ('session', 'score', 'total_marks', 'created_at')


# ✅ SUBJECT ADMIN WITH QUESTION COUNT
@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'description',
        'is_active',
        'question_count',
    )
    list_filter = ('is_active',)
    search_fields = ('name',)

    def question_count(self, obj):
        return obj.question_set.count()

    question_count.short_description = "Questions"


# ✅ REGISTER OTHERS (ONLY ONCE)
admin.site.register(User, UserAdmin)
admin.site.register(StudentSubjectEnrollment, StudentSubjectEnrollmentAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(Exam, ExamAdmin)
admin.site.register(ExamSession, ExamSessionAdmin)
admin.site.register(Answer)
admin.site.register(Result, ResultAdmin)
admin.site.register(EmailOTP)
