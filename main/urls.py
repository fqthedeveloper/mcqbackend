from django.urls import path, include
from rest_framework import routers
from . import views
from .views import LoginView

router = routers.DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'subjects', views.SubjectViewSet)
router.register(r'questions', views.QuestionViewSet)
router.register(r'exams', views.ExamViewSet)
router.register(r'sessions', views.ExamSessionViewSet)
router.register(r'answers', views.AnswerViewSet)
router.register(r'results', views.ResultViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('login/', LoginView.as_view(), name='login'),

]
