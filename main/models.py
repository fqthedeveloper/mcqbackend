from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.forms import ValidationError
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
        return f"{self.email} - Q{self.first_name}"  # or whatever other fields you want

    groups = models.ManyToManyField(
        Group,
        related_name="customuser_set",  # custom name to avoid clashes
        blank=True,
        help_text="The groups this user belongs to.",
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name="customuser_permissions",  # custom name to avoid clashes
        blank=True,
        help_text="Specific permissions for this user.",
        related_query_name="user",
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
    text = models.TextField(unique=True)  # Unique to prevent duplicate questions
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
        return self.text  


class Exam(models.Model):
    MODE_CHOICES = (
        ('practice', 'Practice'),
        ('strict', 'Strict'),
        ('practical', 'Practical'),
    )
    title = models.CharField(max_length=200)
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='practice')
    duration = models.PositiveIntegerField(help_text="Duration in minutes")
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    questions = models.ManyToManyField('Question', through='ExamQuestion')
    practical_tasks = models.ManyToManyField('PracticalTask', through='ExamPracticalTask')
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.title
    
    def clean(self):
        if self.mode == 'practical' and self.questions.exists():
            raise ValidationError("Practical exams cannot have MCQ questions")

class PracticalTask(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    command_template = models.TextField(help_text="Template command for the task")
    expected_output = models.TextField(help_text="Expected output pattern (regex)")
    marks = models.PositiveIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class ExamPracticalTask(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    task = models.ForeignKey(PracticalTask, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
        unique_together = [('exam', 'task')]
        
    def __str__(self):
        return f"{self.exam.title} - {self.order}"

class ExamSession(models.Model):
    student = models.ForeignKey('User', on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    termination_reason = models.TextField(null=True, blank=True)
    elapsed_time = models.PositiveIntegerField(default=0)
    terminal_output = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = [('student', 'exam')]
        
    def __str__(self):
        return f"{self.student.email} - {self.exam.title}"
    
class ExamQuestion(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
        unique_together = [('exam', 'question')]
        
    def __str__(self):
        return f"{self.exam.title} - {self.order}"

class PracticalAnswer(models.Model):
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE)
    task = models.ForeignKey(PracticalTask, on_delete=models.CASCADE)
    command_used = models.TextField()
    output = models.TextField()
    is_verified = models.BooleanField(default=False)
    
    class Meta:
        unique_together = [('session', 'task')]
    
    def __str__(self):
        return f"Answer for {self.task}"

class Answer(models.Model):
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_answers = models.CharField(max_length=50)  # Comma-separated: "A,C"
    
    class Meta:
        unique_together = [('session', 'question')]
    
    def __str__(self):
        return f"Answer for {self.question}"

class Result(models.Model):
    session = models.OneToOneField(ExamSession, on_delete=models.CASCADE)
    score = models.PositiveIntegerField()
    total_marks = models.PositiveIntegerField()
    details = models.JSONField()  
    
    def __str__(self):
        return f"Result: {self.session} - {self.score}/{self.total_marks}"
