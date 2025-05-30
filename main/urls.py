from django.urls import path, include
from rest_framework import routers
from . import views
from .views import LoginView, ForcePasswordChangeView

router = routers.DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'subjects', views.SubjectViewSet, basename='subject')
router.register(r'questions', views.QuestionViewSet, basename='questions')
router.register(r'exams', views.ExamViewSet, basename='exam')
router.register(r'sessions', views.ExamSessionViewSet, basename='session')
router.register(r'answers', views.AnswerViewSet, basename='answer')
router.register(r'results', views.ResultViewSet, basename='result')
router.register(r'students', views.StudentViewSet, basename='student')

urlpatterns = [
    path('', include(router.urls)),
    path('login/', LoginView.as_view(), name='login'),
    path('change-password/', ForcePasswordChangeView.as_view(), name='change-password'),
    path('exams/<int:pk>/publish/', views.ExamViewSet.as_view({'post': 'publish'}), name='exam-publish'),
    path('exams/<int:pk>/unpublish/', views.ExamViewSet.as_view({'post': 'unpublish'}), name='exam-unpublish'),
    path('sessions/<int:pk>/start/', views.ExamSessionViewSet.as_view({'post': 'start_exam'}), name='session-start'),
    path('sessions/<int:pk>/submit/', views.ExamSessionViewSet.as_view({'post': 'submit_exam'}), name='session-submit'),
]