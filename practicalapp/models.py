# ==========================================
# MODELS.PY (FULL UPDATED VERSION)
# ==========================================

from django.db import models
from django.conf import settings
from django.utils import timezone
from mcqapp.models import Subject
from django.db.models import Q
from ckeditor.fields import RichTextField

User = settings.AUTH_USER_MODEL


class PracticalTask(models.Model):
    title = models.CharField(max_length=200, unique=True)
    description = RichTextField()

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="practical_exams"
    )

    init_script = models.TextField()
    verify_script = models.TextField()

    total_marks = models.IntegerField(default=10)
    duration_minutes = models.IntegerField(default=60)

    is_published = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.init_script:
            self.init_script = self.init_script.replace("\r\n", "\n").strip() + "\n"

        if self.verify_script:
            self.verify_script = self.verify_script.replace("\r\n", "\n").strip() + "\n"

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class PracticalSession(models.Model):

    STATUS_CHOICES = (
        ("starting", "Starting"),
        ("running", "Running"),
        ("submitted", "Submitted"),
        ("expired", "Expired"),
        ("terminated", "Terminated"),
        ("failed", "Failed"),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="practical_sessions"
    )

    task = models.ForeignKey(
        "practicalapp.PracticalTask",
        on_delete=models.CASCADE,
        related_name="sessions"
    )

    vm_name = models.CharField(max_length=150, unique=True, null=True, blank=True)
    vm_ip = models.GenericIPAddressField(null=True, blank=True)

    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)

    # ===============================
    # RESULT STORAGE
    # ===============================
    obtained_marks = models.IntegerField(default=0)
    percentage = models.FloatField(default=0.0)

    verification_output = models.TextField(blank=True, null=True)
    verification_details = models.JSONField(blank=True, null=True)
    is_passed = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="starting",
        db_index=True
    )

    history_path = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status__in=["starting", "running"]),
                name="one_active_practical_per_user"
            )
        ]

    def calculate_percentage(self):
        if self.task.total_marks > 0:
            self.percentage = round(
                (self.obtained_marks / self.task.total_marks) * 100,
                2
            )
        else:
            self.percentage = 0.0

    def __str__(self):
        return f"{self.user} | {self.task.title} | {self.status}"
