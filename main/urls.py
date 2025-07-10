from django.urls import path, include
from rest_framework import routers
from .views import (
    UserViewSet,
    SubjectViewSet,
    QuestionViewSet,
    ExamViewSet,
    ExamSessionViewSet,
    AnswerViewSet,
    ResultViewSet,
    StudentViewSet,
    PracticalExamViewSet,
    PracticalExamSessionViewSet,
    PracticalExamResultViewSet,
    LoginView,
    ForcePasswordChangeView,
    SendOTPView,
    VerifyOTPView
)

router = routers.DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'subjects', SubjectViewSet, basename='subject')
router.register(r'questions', QuestionViewSet, basename='questions')
router.register(r'exams', ExamViewSet, basename='exam')
router.register(r'sessions', ExamSessionViewSet, basename='session')
router.register(r'answers', AnswerViewSet, basename='answer')
router.register(r'results', ResultViewSet, basename='result')
router.register(r'students', StudentViewSet, basename='student')
router.register(r'practical-exams', PracticalExamViewSet, basename='practical-exam')
router.register(r'practical-sessions', PracticalExamSessionViewSet, basename='practical-session')
router.register(r'practical-results', PracticalExamResultViewSet, basename='practical-result')

urlpatterns = [
    path('', include(router.urls)),
    path('login/', LoginView.as_view(), name='login'),
    path('change-password/', ForcePasswordChangeView.as_view(), name='change-password'),
    path('exams/<int:pk>/publish/', ExamViewSet.as_view({'post': 'publish'}), name='exam-publish'),
    path('exams/<int:pk>/unpublish/', ExamViewSet.as_view({'post': 'unpublish'}), name='exam-unpublish'),
    path('sessions/<int:pk>/start/', ExamSessionViewSet.as_view({'post': 'start_exam'}), name='session-start'),
    path('sessions/<int:pk>/submit/', ExamSessionViewSet.as_view({'post': 'submit_exam'}), name='session-submit'),
    path('sessions/validate-exam/<int:pk>', ExamSessionViewSet.as_view({'post': 'validate_exam'}), name='validate-exam'),

    path('practical-sessions/<int:pk>/container_status/', PracticalExamSessionViewSet.as_view({'post': 'container_status'}), name='container-status'),
    path('practical-sessions/<int:pk>/reset_container/', PracticalExamSessionViewSet.as_view({'post': 'container_reset'}), name='container-reset'),

    path('send-otp/', SendOTPView.as_view(), name='send_otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
]
