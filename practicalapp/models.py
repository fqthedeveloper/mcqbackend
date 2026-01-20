from django.db import models
from django.conf import settings
from django.utils import timezone
from mcqapp.models import Subject

User = settings.AUTH_USER_MODEL


class PracticalTask(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="practical_exams"
    )

    snapshot_name = models.CharField(max_length=100)
    verify_command = models.TextField()
    expected_output = models.CharField(max_length=200)

    total_marks = models.IntegerField(default=10)
    duration_minutes = models.IntegerField(default=60)

    is_published = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.subject.name})"


class PracticalSession(models.Model):
    STATUS_CHOICES = (
        ("running", "Running"),
        ("submitted", "Submitted"),
        ("expired", "Expired"),
        ("terminated", "Terminated"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    task = models.ForeignKey(PracticalTask, on_delete=models.CASCADE)

    vm_name = models.CharField(max_length=120, unique=True)
    vm_ip = models.GenericIPAddressField()

    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)

    obtained_marks = models.IntegerField(default=0)
    percentage = models.FloatField(default=0.0)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="running"
    )

    def calculate_percentage(self):
        if self.task.total_marks > 0:
            self.percentage = round(
                (self.obtained_marks / self.task.total_marks) * 100, 2
            )
        else:
            self.percentage = 0

    def __str__(self):
        return f"{self.user} | {self.task}"
