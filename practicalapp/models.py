from django.db import models
from django.conf import settings
from django.utils import timezone
from mcqapp.models import Subject
from django.db.models import Q


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

    init_script = models.TextField(
        help_text="Executed at VM boot to prepare/break environment"
    )

    verify_script = models.TextField(
        help_text="Executed at submission time"
    )

    total_marks = models.IntegerField(default=10)
    duration_minutes = models.IntegerField(default=60)

    is_published = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # 🔥 CRITICAL: normalize scripts for Linux
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

    # =========================
    # RELATIONS
    # =========================
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="practical_sessions"
    )

    task = models.ForeignKey(
        "practicalapp.PracticalTask",   # ✅ FIXED
        on_delete=models.CASCADE,
        related_name="sessions"
    )

    # =========================
    # VM INFO (SET AFTER VM UP)
    # =========================
    vm_name = models.CharField(
        max_length=150,
        unique=True,
        null=True,      # ✅ MUST be nullable
        blank=True      # ✅ MUST be blank
    )

    vm_ip = models.GenericIPAddressField(
        null=True,
        blank=True
    )

    # =========================
    # TIMING
    # =========================
    start_time = models.DateTimeField(
        default=timezone.now
    )

    end_time = models.DateTimeField(
        null=True,
        blank=True
    )

    # =========================
    # RESULT
    # =========================
    obtained_marks = models.IntegerField(
        default=0
    )

    percentage = models.FloatField(
        default=0.0
    )

    # =========================
    # STATUS
    # =========================
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="starting",
        db_index=True
    )
    
    history_path = models.CharField(
        max_length=500,
        blank=True,
        null=True
    
    )

    # =========================
    # DB-LEVEL PROTECTION
    # =========================
    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["vm_name"]),
        ]
        constraints = [
            # ❌ PREVENT MULTIPLE ACTIVE SESSIONS PER USER
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status__in=["starting", "running"]),
                name="one_active_practical_per_user"
            )
        ]

    # =========================
    # METHODS
    # =========================
    def calculate_percentage(self):
        if self.task.total_marks > 0:
            self.percentage = round(
                (self.obtained_marks / self.task.total_marks) * 100,
                2
            )
        else:
            self.percentage = 0.0

    def mark_submitted(self):
        self.status = "submitted"
        self.end_time = timezone.now()
        self.calculate_percentage()
        self.save(
            update_fields=[
                "status",
                "end_time",
                "obtained_marks",
                "percentage"
            ]
        )

    def mark_failed(self):
        self.status = "failed"
        self.end_time = timezone.now()
        self.save(update_fields=["status", "end_time"])

    def mark_expired(self):
        self.status = "expired"
        self.end_time = timezone.now()
        self.save(update_fields=["status", "end_time"])

    def terminate(self):
        self.status = "terminated"
        self.end_time = timezone.now()
        self.save(update_fields=["status", "end_time"])

    def __str__(self):
        return f"{self.user} | {self.task.title} | {self.status}"
