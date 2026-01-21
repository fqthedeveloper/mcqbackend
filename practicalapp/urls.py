from django.urls import path
from . import views

urlpatterns = [

    # ADMIN
    path("tasks/", views.admin_practical_list_create),
    path("tasks/<int:pk>/", views.admin_practical_update),

    # STUDENT
    path("student-exams/", views.student_practical_list),
    path("student-exams/<int:pk>/detail/", views.student_practical_detail),
    path("student-exams/<int:pk>/start/", views.student_practical_start),

    # SESSION
    path("sessions/<int:pk>/", views.practical_session_detail),
    path("sessions/<int:pk>/submit/", views.practical_session_submit),
]
