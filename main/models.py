from asyncio.log import logger
import secrets
from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import os
import shutil
from django.utils import timezone
import docker



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
    questions = models.ManyToManyField(Question, through='ExamQuestion')
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
    description = models.TextField()
    duration = models.PositiveIntegerField(help_text="Duration in minutes")
    docker_image = models.CharField(
        max_length=255,
        default="redhat/ubi8:latest",
        help_text="Docker image to use for the exam"
    )
    setup_command = models.TextField(
        help_text="Command to run when session starts",
        default="echo 'Environment ready'"
    )
    verification_command = models.TextField(
        help_text="Command to verify solution",
        default="echo 'Verification complete'"
    )
    environment_vars = models.JSONField(
        default=dict,
        blank=True,
        help_text="Environment variables (JSON key-value pairs)"
    )
    allowed_commands = models.JSONField(
        default=list,
        blank=True,
        help_text="List of allowed commands (empty for all)"
    )
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
    
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    exam = models.ForeignKey('PracticalExam', on_delete=models.CASCADE)
    container_id = models.CharField(max_length=64, null=True, blank=True)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    verification_output = models.TextField(blank=True, null=True)
    is_success = models.BooleanField(default=False)
    termination_reason = models.TextField(null=True, blank=True)
    token = models.CharField(max_length=100, default=secrets.token_urlsafe, unique=True)

    class Meta:
        unique_together = [('student', 'exam')]
        ordering = ['-start_time']
        
    def __str__(self):
        return f"{self.student.username} - {self.exam.title}"
    
    def start_container(self):
        client = docker.from_env()
        environment = {
            **self.exam.environment_vars,
            "STUDENT_ID": str(self.student.id),
            "EXAM_ID": str(self.exam.id)
        }
        
        try:
            container = client.containers.run(
                image=self.exam.docker_image,
                command="sleep infinity",
                detach=True,
                tty=True,
                environment=environment,
                working_dir="/exam",
                volumes={
                    f"{settings.BASE_DIR}/exam_data/{self.id}": {
                        'bind': '/exam', 
                        'mode': 'rw'
                    }
                },
                name=f"practical-exam-{self.id}",
                stdin_open=True,
            )
            self.container_id = container.id
            self.save()
            
            if self.exam.setup_command:
                exit_code, output = container.exec_run(
                    f"sh -c '{self.exam.setup_command}'",
                    workdir="/exam",
                    tty=True
                )
                logger.info(f"Setup command executed: {exit_code}")
            
            return container
        except docker.errors.ImageNotFound:
            logger.error(f"Image not found: {self.exam.docker_image}")
            raise Exception(f"Docker image {self.exam.docker_image} not found")
        except docker.errors.APIError as e:
            logger.error(f"Docker API error: {str(e)}")
            raise Exception(f"Docker error: {str(e)}")
        except Exception as e:
            logger.exception("Container start failed")
            raise Exception(f"Failed to start container: {str(e)}")
    
    def terminate_container(self):
        client = docker.from_env()
        try:
            if self.container_id:
                container = client.containers.get(self.container_id)
                container.stop(timeout=2)
                container.remove()
                self.container_id = None
                self.save()
        except Exception as e:
            logger.error(f"Error terminating container: {str(e)}")
    
    def execute_command(self, command):
        client = docker.from_env()
        try:
            container = client.containers.get(self.container_id)
            exit_code, output = container.exec_run(
                f"sh -c '{command}'",
                workdir="/exam"
            )
            return output.decode('utf-8')
        except Exception as e:
            return f"Command execution failed: {str(e)}"

class PracticalExamResult(models.Model):
    session = models.ForeignKey(PracticalExamSession, on_delete=models.CASCADE)
    score = models.PositiveIntegerField()
    total_possible = models.PositiveIntegerField()
    details = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Result for {self.session}"