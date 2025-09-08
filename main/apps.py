# mcqbackend/main/apps.py
from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.db.utils import OperationalError, ProgrammingError


def load_verification_scripts(sender, **kwargs):
    """
    Load and register verification scripts after migrations are applied.
    Skip if tables are not ready yet.
    """
    try:
        from .models import PracticalExam
        from .verification import verification_system

        exams = PracticalExam.objects.all()
        for exam in exams:
            script_path = (
                f"D:/FQ/Django/MCQ FullStack WEB App/mcqbackend/exam_data/verify_exam_{exam.id}.py"
            )
            verification_system.register_verification_script(exam.id, script_path)

    except (OperationalError, ProgrammingError):
        # Table doesn't exist yet (fresh migrate)
        pass


class MainConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "main"

    def ready(self):
        # Attach the signal, but don’t run DB queries here
        post_migrate.connect(load_verification_scripts, sender=self)
