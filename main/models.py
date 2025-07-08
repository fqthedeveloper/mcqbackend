from asyncio.log import logger
import secrets
import time
from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import os
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
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE)
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
        ('starting', 'Starting'),  # New status
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('terminated', 'Terminated'),
        ('failed', 'Failed'),  # New status for startup failures
    )
    
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    exam = models.ForeignKey('PracticalExam', on_delete=models.CASCADE)
    container_id = models.CharField(max_length=64, null=True, blank=True)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='starting')  # Updated default
    verification_output = models.TextField(blank=True, null=True)
    is_success = models.BooleanField(default=False)
    termination_reason = models.TextField(null=True, blank=True)
    token = models.CharField(max_length=100, default=secrets.token_urlsafe, unique=True)
    startup_log = models.TextField(blank=True, null=True)  # Store startup logs

    class Meta:
        unique_together = [('student', 'exam')]
        ordering = ['-start_time']
        
    def __str__(self):
        return f"{self.student.username} - {self.exam.title} ({self.status})"
    
    def start_container(self):
        """Create and start a Docker container for the exam session"""
        log_lines = []
        
        try:
            client = docker.from_env(timeout=300)
            log_lines.append(f"Docker client initialized")
            
            environment = {
                **self.exam.environment_vars,
                "STUDENT_ID": str(self.student.id),
                "EXAM_ID": str(self.exam.id),
                "TERM": "xterm-256color"
            }
            
            volume_path = os.path.join(settings.BASE_DIR, 'exam_data', str(self.id))
            os.makedirs(volume_path, exist_ok=True)
            log_lines.append(f"Created volume path: {volume_path}")
            
            if os.name == 'nt':
                volume_path = volume_path.replace('\\', '/').replace(':', '')
                volume_path = f'/{volume_path}'
                log_lines.append(f"Converted Windows path: {volume_path}")
            
            # Run container
            container = client.containers.run(
                image=self.exam.docker_image,
                command="sleep infinity",
                detach=True,
                tty=True,
                environment=environment,
                working_dir="/exam",
                volumes={volume_path: {'bind': '/exam', 'mode': 'rw'}},
                name=f"practical-exam-{self.id}",
                stdin_open=True,
            )
            log_lines.append(f"Container created: {container.id}")
            
            self.container_id = container.id
            self.status = 'running'
            self.save()
            log_lines.append("Container ID saved to session")
            
            # Wait for container to be fully started
            self._wait_for_container(client, container, log_lines)
            
            # Execute setup command if defined
            if self.exam.setup_command:
                log_lines.append(f"Executing setup command: {self.exam.setup_command}")
                self._execute_setup_command(client, container, log_lines)
                
            log_lines.append("Container started successfully")
            
        except docker.errors.ImageNotFound:
            error_msg = f"Image not found: {self.exam.docker_image}"
            log_lines.append(error_msg)
            self.status = 'failed'
            self.termination_reason = error_msg
            logger.error(error_msg)
        except docker.errors.APIError as e:
            error_msg = f"Docker API error: {str(e)}"
            log_lines.append(error_msg)
            self.status = 'failed'
            self.termination_reason = error_msg
            logger.error(error_msg)
        except Exception as e:
            error_msg = f"Container startup failed: {str(e)}"
            log_lines.append(error_msg)
            self.status = 'failed'
            self.termination_reason = error_msg
            logger.exception("Container startup failed")
        finally:
            self.startup_log = "\n".join(log_lines)
            self.save()
    
    def _wait_for_container(self, client, container, log_lines, max_retries=20, delay=2):
        """Wait for container to reach running state"""
        for i in range(max_retries):
            try:
                container.reload()
                if container.status == 'running':
                    log_lines.append(f"Container running after {i+1} checks")
                    return
                log_lines.append(f"Container status: {container.status} (check {i+1})")
            except docker.errors.NotFound:
                log_lines.append(f"Container not found during check {i+1}")
            except Exception as e:
                log_lines.append(f"Error checking container: {str(e)}")
                
            time.sleep(delay)
        
        error_msg = f"Timed out waiting for container to start after {max_retries*delay} seconds"
        log_lines.append(error_msg)
        raise Exception(error_msg)
    
    def _execute_setup_command(self, client, container, log_lines):
        """Execute setup command in container"""
        try:
            exit_code, output = container.exec_run(
                cmd=self.exam.setup_command,
                workdir="/exam",
                tty=True
            )
            output = output.decode('utf-8') if isinstance(output, bytes) else output
            log_lines.append(f"Setup command executed. Exit code: {exit_code}")
            log_lines.append(f"Command output:\n{output[:1000]}")
            
            if exit_code != 0:
                log_lines.append(f"Warning: Setup command exited with code {exit_code}")
        except Exception as e:
            error_msg = f"Setup command failed: {str(e)}"
            log_lines.append(error_msg)
            raise Exception(error_msg)
    
    def terminate_container(self):
        if not self.container_id:
            return
            
        try:
            client = docker.from_env()
            container = client.containers.get(self.container_id)
            container.stop(timeout=5)
            container.remove(v=True, force=True)
            logger.info(f"Container terminated: {self.container_id}")
            self.container_id = None
            self.save()
        except docker.errors.NotFound:
            logger.warning(f"Container not found during termination: {self.container_id}")
        except Exception as e:
            logger.error(f"Container termination failed: {str(e)}")
            raise Exception(f"Failed to clean up exam environment: {str(e)}")
    
    def execute_command(self, command):
        if not self.container_id:
            return "No active container"
            
        try:
            client = docker.from_env()
            container = client.containers.get(self.container_id)
            exit_code, output = container.exec_run(
                command,
                workdir="/exam"
            )
            return output.decode('utf-8')
        except Exception as e:
            return f"Command execution failed: {str(e)}"
    
    def get_container_status(self):
        if not self.container_id:
            return 'not created'
            
        try:
            client = docker.from_env()
            container = client.containers.get(self.container_id)
            return container.status
        except docker.errors.NotFound:
            return 'not found'
        except Exception as e:
            logger.error(f"Container status error: {str(e)}")
            return 'error'
    
    def save(self, *args, **kwargs):
        if self.status in ['completed', 'terminated'] and self.container_id:
            self.terminate_container()
        super().save(*args, **kwargs)


        
class PracticalExamResult(models.Model):
    session = models.ForeignKey(PracticalExamSession, on_delete=models.CASCADE)
    score = models.FloatField()
    total_possible = models.FloatField()
    details = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Result for {self.session}"