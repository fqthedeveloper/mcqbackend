# mcqbackend/main/apps.py
from django.apps import AppConfig
from django.db.models.signals import post_migrate


def load_verification_scripts(sender, **kwargs):
    """
    Load and register verification scripts after migrations are applied.
    This avoids querying the database during Django app initialization.
    """
    from .models import PracticalExam
    from .verification import verification_system

    exams = PracticalExam.objects.all()
    for exam in exams:
        script_path = (
            f"D:/FQ/Django/MCQ FullStack WEB App/mcqbackend/exam_data/verify_exam_{exam.id}.py"
        )
        verification_system.register_verification_script(exam.id, script_path)


class MainConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "main"

    def ready(self):
        # Only attach signal here, no DB queries
        post_migrate.connect(load_verification_scripts, sender=self)
