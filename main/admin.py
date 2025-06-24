from django.contrib import admin
from .models import *

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'first_name', 'last_name', 'user_type', 'is_verified']

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name']

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['text', 'subject', 'marks', 'is_multi']

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['title', 'subject', 'mode', 'is_published']

@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display = ['exam', 'question', 'order']

@admin.register(ExamSession)
class ExamSessionAdmin(admin.ModelAdmin):
    list_display = ['student', 'exam', 'start_time', 'is_completed']

@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ['session', 'question', 'selected_answers']

@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ['session', 'score', 'total_marks']


@admin.register(PracticalExam)
class PracticalExamAdmin(admin.ModelAdmin):
    list_display = ['title', 'docker_image', 'description', 'created_at', 'is_published']

@admin.register(PracticalExamSession)
class PracticalExamSessionAdmin(admin.ModelAdmin):
    list_display = ['student', 'exam', 'start_time', 'status']

@admin.register(PracticalExamResult)
class PracticalExamResultAdmin(admin.ModelAdmin):
    list_display = ['session', 'score', 'total_possible', 'created_at']