from django.contrib import admin
from .models import User, Subject, Question, Exam, ExamQuestion, ExamSession, Answer, Result
# Register your models here.

admin.site.register(User)
admin.site.register(Subject)
admin.site.register(Question)
admin.site.register(Exam)
admin.site.register(ExamQuestion)
admin.site.register(ExamSession)
admin.site.register(Answer)
admin.site.register(Result)
