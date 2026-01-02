from django.urls import path, include
from rest_framework import routers
from .views import (
    UserViewSet, SubjectViewSet, QuestionViewSet,
    ExamViewSet, ExamSessionViewSet, AnswerViewSet,
    ResultViewSet, StudentViewSet, StudentSubjectEnrollmentViewSet,
    SendOTPView, LoginView, ForcePasswordChangeView, VerifyOTPView,
    StudentDashboardView, AdminDashboardView, MyProfileView
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
router.register(r'enrollments', StudentSubjectEnrollmentViewSet, basename='enrollment')

urlpatterns = [
    path('', include(router.urls)),

    # Auth
    path('login/', LoginView.as_view(), name='login'),
    path('change-password/', ForcePasswordChangeView.as_view(), name='change-password'),
    path('send-otp/', SendOTPView.as_view(), name='send-otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),

    # Dashboard
    path('student-dashboard/', StudentDashboardView.as_view(), name='student-dashboard'),
    path('admin-dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('my-profile/', MyProfileView.as_view(), name='my-profile'),

    # Exam actions
    path('exams/<int:pk>/publish/', ExamViewSet.as_view({'post': 'publish'})),
    path('exams/<int:pk>/unpublish/', ExamViewSet.as_view({'post': 'unpublish'})),
    path('sessions/<int:pk>/start/', ExamSessionViewSet.as_view({'post': 'start_exam'})),
    path('sessions/<int:pk>/submit/', ExamSessionViewSet.as_view({'post': 'submit_exam'})),
    path('sessions/validate/<int:exam_id>/', ExamSessionViewSet.as_view({'get': 'validate_session'})),

    # Bulk
    path('enrollments/bulk-enroll/', StudentSubjectEnrollmentViewSet.as_view({'post': 'bulk_enroll'})),
    path('enrollments/bulk-assign/', StudentSubjectEnrollmentViewSet.as_view({'post': 'bulk_assign_subjects'})),
]
