from django.urls import path
from .views import (
    available_practicals, start_practical, submit_practical, practical_task_list_create, practical_task_update 

)


urlpatterns = [
     # ADMIN CRUD
    path("tasks/", practical_task_list_create),
    path("tasks/<int:pk>/", practical_task_update),
    
    path("available/", available_practicals),
    path("start/", start_practical),
    path("submit/", submit_practical),
]
