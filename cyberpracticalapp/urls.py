from django.urls import path
from . import views

urlpatterns = [

    # =====================================================
    # ADMIN
    # =====================================================

    path(
        "admin/machine-templates/",
        views.admin_machine_templates
    ),

    path(
        "admin/topologies/",
        views.admin_topologies
    ),

    path(
        "admin/tasks/",
        views.admin_tasks
    ),

    path(
        "admin/tasks/<int:pk>/",
        views.admin_task_detail
    ),

    # =====================================================
    # STUDENT TASKS
    # =====================================================

    path(
        "student/tasks/",
        views.student_task_list
    ),

    path(
        "student/tasks/<int:pk>/",
        views.student_task_detail
    ),

    # =====================================================
    # SESSION
    # =====================================================

    path(
        "student/start/<int:pk>/",
        views.start_cyber_practical
    ),

    path(
        "student/session/<int:pk>/",
        views.get_session
    ),

    path(
        "student/session/<int:pk>/submit/",
        views.submit_session
    ),
    path(
        "student/cyber/active-session/",
        views.get_active_cyber_session
    ),

    # =====================================================
    # RESULTS
    # =====================================================

    path(
        "student/results/",
        views.student_results
    ),

    path(
        "admin/results/",
        views.admin_results
    ),

]