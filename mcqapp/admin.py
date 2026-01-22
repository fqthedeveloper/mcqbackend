from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import Count
from .models import *




# =========================
# USER ADMIN
# =========================

class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'username', 'user_type', 'is_active')
    ordering = ('email',)
    search_fields = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('User Type', {'fields': ('user_type',)}),
        ('Force Password Change', {'fields': ('force_password_change',)}),
        ('User Email Verified', {'fields': ('is_verified',)}),
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


# =========================
# SUBJECT ADMIN (WITH COUNTS)
# =========================

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'is_active',
        'question_count',
        'practice_easy_count',
        'practice_medium_count',
        'practice_hard_count',
    )
    list_filter = ('is_active',)
    search_fields = ('name',)

    def question_count(self, obj):
        return Question.objects.filter(subject=obj).count()

    def practice_easy_count(self, obj):
        return PracticeQuestion.objects.filter(subject=obj, difficulty="easy").count()

    def practice_medium_count(self, obj):
        return PracticeQuestion.objects.filter(subject=obj, difficulty="medium").count()

    def practice_hard_count(self, obj):
        return PracticeQuestion.objects.filter(subject=obj, difficulty="hard").count()

    question_count.short_description = "Questions"
    practice_easy_count.short_description = "Practice Easy"
    practice_medium_count.short_description = "Practice Medium"
    practice_hard_count.short_description = "Practice Hard"


# =========================
# ENROLLMENT ADMIN
# =========================

class StudentSubjectEnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'is_active')
    list_filter = ('is_active', 'subject')
    search_fields = ('student__email',)


# =========================
# QUESTION ADMIN
# =========================

class QuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'subject', 'marks')
    list_filter = ('subject',)
    search_fields = ('text',)


# =========================
# PRACTICE QUESTION ADMIN
# =========================

@admin.register(PracticeQuestion)
class PracticeQuestionAdmin(admin.ModelAdmin):
    list_display = (
        'question_text',
        'subject',
        'difficulty',
    )
    list_filter = ('subject', 'difficulty')
    search_fields = ('question__text',)

    def question_text(self, obj):
        return obj.question.text[:80]

    question_text.short_description = "Question"


# =========================
# PRACTICE RUN ADMIN
# =========================

@admin.register(PracticeRun)
class PracticeRunAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'subject',
        'difficulty',
        'duration_minutes',
        'started_at',
    )
    list_filter = ('difficulty', 'subject')
    search_fields = ('student__email',)
    date_hierarchy = 'started_at'


# =========================
# PRACTICE ANSWER ADMIN
# =========================

@admin.register(PracticeAnswer)
class PracticeAnswerAdmin(admin.ModelAdmin):
    list_display = (
        'student_email',
        'subject',
        'difficulty',
        'is_correct',
    )
    list_filter = ('is_correct', 'practice_question__difficulty')
    search_fields = ('run__student__email', 'practice_question__question__text')

    def student_email(self, obj):
        return obj.run.student.email

    def subject(self, obj):
        return obj.practice_question.subject.name

    def difficulty(self, obj):
        return obj.practice_question.difficulty

    student_email.short_description = "Student"
    subject.short_description = "Subject"
    difficulty.short_description = "Difficulty"


# =========================
# EXAM ADMIN (ORIGINAL)
# =========================

class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'mode', 'is_published')
    list_filter = ('subject', 'mode')
    search_fields = ('title',)


class ExamSessionAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'is_completed')
    list_filter = ('is_completed',)


class ResultAdmin(admin.ModelAdmin):
    list_display = ('session', 'score', 'total_marks', 'created_at')
    date_hierarchy = 'created_at'


# =========================
# REGISTER REMAINING MODELS
# =========================

admin.site.register(User, UserAdmin)
admin.site.register(StudentSubjectEnrollment, StudentSubjectEnrollmentAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(Exam, ExamAdmin)
admin.site.register(ExamSession, ExamSessionAdmin)
admin.site.register(Answer)
admin.site.register(Result, ResultAdmin)
admin.site.register(EmailOTP)

