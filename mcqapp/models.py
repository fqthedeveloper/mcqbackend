from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.utils import timezone
import uuid


class User(AbstractUser):
    USER_TYPES = (
        ('admin', 'Admin'),
        ('student', 'Student'),
    )

    user_type = models.CharField(max_length=10, choices=USER_TYPES, default='student')
    email = models.EmailField(unique=True)

    is_verified = models.BooleanField(default=False)
    force_password_change = models.BooleanField(default=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    groups = models.ManyToManyField(Group, related_name="customuser_set", blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name="customuser_permissions", blank=True)

    def __str__(self):
        return self.email


class PasswordResetToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=30)

class EmailOTP(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_otp"
    )
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=10)

    def __str__(self):
        return f"{self.user.email} - {self.otp}"


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class StudentSubjectEnrollment(models.Model):
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="enrollments"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('student', 'subject')

    def __str__(self):
        return f"{self.student.email} → {self.subject.name}"


class Question(models.Model):
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE)
    text = models.CharField(max_length=1000)

    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)

    correct_option = models.CharField(max_length=20)
    marks = models.PositiveIntegerField(default=1)
    explanation = models.TextField(blank=True)

    class Meta:
        unique_together = ('subject', 'text')

    def __str__(self):
        return self.text[:60]


class Exam(models.Model):
    MODE_CHOICES = (
        ('practice', 'Practice'),
        ('strict', 'Strict'),
    )

    title = models.CharField(max_length=200)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    duration = models.PositiveIntegerField(help_text="Minutes")
    mode = models.CharField(max_length=10, choices=MODE_CHOICES)

    questions = models.ManyToManyField(
        Question,
        related_name="exams",
        blank=True
    )

    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class ExamSession(models.Model):
    TERMINATE_CHOICES = (
        ("time_up", "Time Up"),
        ("warnings", "Warnings Limit"),
        ("manual", "Manual Submit"),
    )

    student = models.ForeignKey(User, on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)

    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)

    terminate_reason = models.CharField(
        max_length=20,
        choices=TERMINATE_CHOICES,
        null=True,
        blank=True,
    )

    class Meta:
        unique_together = ("student", "exam")

    def __str__(self):
        return f"{self.student} - {self.exam}"

class Answer(models.Model):
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_answers = models.CharField(max_length=50)


class Result(models.Model):
    session = models.OneToOneField(ExamSession, on_delete=models.CASCADE)
    score = models.PositiveIntegerField()
    total_marks = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)



# ===== PRACTICE MODELS =====

class PracticeQuestion(models.Model):
    DIFFICULTY_CHOICES = (
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    )

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES)

    class Meta:
        # ❗ A QUESTION CAN EXIST ONLY ONCE PER SUBJECT (ANY DIFFICULTY)
        unique_together = ("subject", "question")

    def __str__(self):
        return f"{self.subject.name} | {self.question.id} | {self.difficulty}"
    

class PracticeRun(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    difficulty = models.CharField(max_length=10)
    started_at = models.DateTimeField(auto_now_add=True)
    duration_minutes = models.PositiveIntegerField()


class PracticeAnswer(models.Model):
    run = models.ForeignKey(PracticeRun, on_delete=models.CASCADE)
    practice_question = models.ForeignKey(PracticeQuestion, on_delete=models.CASCADE)
    selected_answers = models.CharField(max_length=50)
    is_correct = models.BooleanField()
    
    
