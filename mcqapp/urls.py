from django.urls import path, include
from rest_framework import routers
from .views import (
    ResetPasswordView, UserViewSet, SubjectViewSet, QuestionViewSet,
    ExamViewSet, ExamSessionViewSet, AnswerViewSet,
    ResultViewSet, StudentViewSet, ForgotPasswordView, PracticeStatsView,
    SendOTPView, LoginView, ForcePasswordChangeView, VerifyOTPView, PracticeQuestionMapView,
    StudentDashboardView, AdminDashboardView, MyProfileView, StartPractice, SubmitPracticeAnswer, FinishPractice
)

router = routers.DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'subjects', SubjectViewSet, basename='subject')
router.register(r'questions', QuestionViewSet, basename='question')
router.register(r'exams', ExamViewSet, basename='exam')
router.register(r'sessions', ExamSessionViewSet, basename='session')
router.register(r'answers', AnswerViewSet, basename='answer')
router.register(r'results', ResultViewSet, basename='result')
router.register(r'students', StudentViewSet, basename='student')

urlpatterns = [
    path('', include(router.urls)),

    # Auth
    path('login/', LoginView.as_view(), name='login'),
    path('change-password/', ForcePasswordChangeView.as_view(), name='change-password'),
    path("forgot-password/", ForgotPasswordView.as_view()),
    path("reset-password/", ResetPasswordView.as_view()),
    path("send-otp/", SendOTPView.as_view(), name="send-otp"),
    path("verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),

    # Dashboard
    path('student-dashboard/', StudentDashboardView.as_view(), name='student-dashboard'),
    path('admin-dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('my-profile/', MyProfileView.as_view(), name='my-profile'),

    # Exam actions
    path('exams/<int:pk>/publish/', ExamViewSet.as_view({'post': 'publish'})),
    path('exams/<int:pk>/unpublish/', ExamViewSet.as_view({'post': 'unpublish'})),
    
    path("practice/admin/map/", PracticeQuestionMapView.as_view(),),
    path("practice/admin/stats/", PracticeStatsView.as_view(),),
        
    path("practice/start/", StartPractice.as_view()),
    path("practice/answer/", SubmitPracticeAnswer.as_view()),
    path("practice/finish/", FinishPractice.as_view()),
]
