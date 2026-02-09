# practicalapp/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path("tasks/", views.admin_practical_list_create),
    path("tasks/<int:pk>/", views.admin_practical_update),

    path("student-exams/", views.student_practical_list),
    path("student-exams/<int:pk>/detail/", views.student_practical_detail),
    path("student-exams/<int:pk>/start/", views.student_practical_start),

    path("sessions/<int:pk>/", views.get_practical_session),
    path("sessions/<int:pk>/submit/", views.practical_session_submit),
]
