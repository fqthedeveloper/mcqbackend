from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class User(AbstractUser):
    USER_TYPES = (
        ('admin', 'Admin'),
        ('student', 'Student'),
    )
    user_type = models.CharField(max_length=10, choices=USER_TYPES)
    is_verified = models.BooleanField(default=False)
    force_password_change = models.BooleanField(default=True)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email

    # Fix related_name conflicts
    groups = models.ManyToManyField(
        'auth.Group',
        related_name="custom_user_groups",
        blank=True,
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name="custom_user_permissions",
        blank=True,
    )

class EmailOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)


class Subject(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self):
        return self.name

class Question(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    text = models.TextField(unique=True)
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_option = models.CharField(max_length=10)
    explanation = models.TextField(blank=True, null=True)
    marks = models.PositiveIntegerField()
    is_multi = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    def __str__(self):
        return self.text[:50]

class Exam(models.Model):
    MODE_CHOICES = (
        ('practice', 'Practice'),
        ('strict', 'Strict'),
        ('practical', 'Practical'),
    )
    title = models.CharField(max_length=200)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='practice')
    duration = models.PositiveIntegerField(help_text="Duration in minutes")
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    practical_exams = models.ManyToManyField('PracticalExam', blank=True) 
    question_count = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Only calculate question count for non-practical exams
        if self.mode != 'practical':
            self.question_count = self.examquestion_set.count()
        super().save(*args, **kwargs)


class ExamQuestion(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
        unique_together = [('exam', 'question')]
        
    def __str__(self):
        return f"{self.exam.title} - Q{self.order}"

class ExamSession(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    termination_reason = models.TextField(null=True, blank=True)
    elapsed_time = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [('student', 'exam')]
        
    def __str__(self):
        return f"{self.student.email} - {self.exam.title}"

class Answer(models.Model):
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_answers = models.CharField(max_length=50)
    
    class Meta:
        unique_together = [('session', 'question')]
    
    def __str__(self):
        return f"Answer for {self.question.id}"

class Result(models.Model):
    session = models.OneToOneField(ExamSession, on_delete=models.CASCADE)
    score = models.PositiveIntegerField()
    total_marks = models.PositiveIntegerField()
    details = models.JSONField()  
    
    def __str__(self):
        return f"Result: {self.session.id} - {self.score}/{self.total_marks}"

class PracticalExam(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    docker_image = models.CharField(max_length=255)
    setup_command = models.TextField(help_text="Command to run when container starts")
    verification_command = models.TextField(help_text="Command to verify solution")
    description = models.TextField()
    duration = models.PositiveIntegerField(help_text="Duration in minutes")
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class PracticalExamSession(models.Model):
    STATUS_CHOICES = (
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('terminated', 'Terminated'),
    )
    
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    exam = models.ForeignKey(PracticalExam, on_delete=models.CASCADE)
    container_id = models.CharField(max_length=64, blank=True, null=True)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    verification_output = models.TextField(blank=True, null=True)
    is_success = models.BooleanField(default=False)
    termination_reason = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = [('student', 'exam')]
        
    def __str__(self):
        return f"{self.student.username} - {self.exam.title}"

class PracticalExamResult(models.Model):
    session = models.OneToOneField(PracticalExamSession, on_delete=models.CASCADE)
    score = models.PositiveIntegerField()
    total_possible = models.PositiveIntegerField()
    details = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Result: {self.session.id} - {self.score}/{self.total_possible}"