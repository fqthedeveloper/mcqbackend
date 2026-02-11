from django.urls import path
from . import views

urlpatterns = [

    # ============================
    # ADMIN TASK MANAGEMENT
    # ============================
    path("tasks/", views.admin_practical_list_create),
    path("tasks/<int:pk>/", views.admin_practical_update),

    # ============================
    # STUDENT PRACTICAL LIST
    # ============================
    path("student-exams/", views.student_practical_list),
    path("student-exams/<int:pk>/detail/", views.student_practical_detail),
    path("student-exams/<int:pk>/start/", views.student_practical_start),

    # ============================
    # SESSION MANAGEMENT
    # ============================
    path("sessions/<int:pk>/", views.get_practical_session),
    path("sessions/<int:pk>/submit/", views.practical_session_submit),

    # ============================
    # RESULTS
    # ============================
    path("student/results/", views.student_practical_results),
    path("admin/results/", views.admin_practical_results),
    path("results/<int:pk>/", views.practical_result_detail),

    # ============================
    # HISTORY
    # ============================
    path("history/<int:pk>/", views.practical_session_history),
    path("history/<int:pk>/file/", views.practical_history_file),
]
