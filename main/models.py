from asyncio.log import logger
import re
import threading
import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.db import models
from django.utils import timezone
import paramiko
from .vbox_manager import vbox_manager


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

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
    subjects = models.ManyToManyField('Subject', related_name='students', blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    objects = UserManager()

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

    # VM settings
    base_vm_name = models.CharField(max_length=255, default="Redhat")
    snapshot_name = models.CharField(max_length=255, default="base_snapshot")
    vm_username = models.CharField(max_length=100, default="kiosk")
    vm_password = models.CharField(max_length=100, default="redhat")

    # Exam settings
    duration_minutes = models.PositiveIntegerField(default=60)
    verification_command = models.TextField(default="echo 'Verification complete'")

    # Publishing + audit fields
    is_published = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class PracticalExamSession(models.Model):
    STATUS_CHOICES = [
        ('starting', 'Starting'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('terminated', 'Terminated'),
        ('failed', 'Failed'),
    ]
    
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    exam = models.ForeignKey('PracticalExam', on_delete=models.CASCADE)
    vm_name = models.CharField(max_length=100, blank=True, default='')
    ssh_port = models.IntegerField(blank=True, null=True)
    token = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='starting')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(blank=True, null=True)
    startup_log = models.TextField(blank=True, default='')
    verification_output = models.TextField(blank=True, default='')
    is_success = models.BooleanField(default=False)
    termination_reason = models.TextField(blank=True, default='')

    def __str__(self):
        return f"{self.student.username} - {self.exam.title}"

    def generate_vm_name(self):
        sanitized_username = re.sub(r'[^a-zA-Z0-9_-]', '_', self.student.username)
        return f"exam-session-{self.id}-{sanitized_username}" if self.id else f"exam-session-temp-{sanitized_username}"

    def generate_ssh_port(self):
        return 2200 + (self.id % 1000) if self.id else 2200

    def start_vm(self):
        from .vbox_manager import vbox_manager
        
        try:
            # Generate unique VM name and SSH port
            self.vm_name = self.generate_vm_name()
            self.ssh_port = self.generate_ssh_port()
            self.token = uuid.uuid4().hex
            self.save()
            
            # Clone VM
            vbox_manager.clone_vm(
                self.exam.base_vm_name,
                self.vm_name,
                self.exam.snapshot_name,
                self.ssh_port
            )
            
            # Start VM
            vbox_manager.start_vm(self.vm_name, headless=True)
            
            # Wait for VM to boot
            if vbox_manager.wait_for_vm_boot(self.vm_name, self.ssh_port):
                self.status = 'running'
                self.startup_log = "VM started successfully"
                self.save()
                
                # Schedule auto-termination at exam end time
                exam_duration = self.exam.duration_minutes * 60  # Convert to seconds
                timer = threading.Timer(
                    exam_duration, 
                    self.auto_terminate,
                    kwargs={'reason': 'Exam time expired'}
                )
                timer.start()
            else:
                self.status = 'failed'
                self.startup_log = "VM failed to boot within timeout"
                self.save()
                
        except Exception as e:
            logger.error(f"Failed to start VM for session {self.id}: {str(e)}")
            self.status = 'failed'
            self.startup_log = str(e)
            self.save()

    def auto_terminate(self, reason="Auto-terminated"):
        self.termination_reason = reason
        self.terminate_vm()
        self.status = 'terminated'
        self.end_time = timezone.now()
        self.save()

    def terminate_vm(self):
        from .vbox_manager import vbox_manager
        if self.vm_name and self.vm_name != '':
            vbox_manager.delete_vm(self.vm_name)
            # Don't set vm_name to None, just clear it
            self.vm_name = ''

    def execute_command(self, command):
        import paramiko
        import socket
        
        if not self.ssh_port:
            raise Exception("SSH port not available")
            
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                '127.0.0.1', 
                port=self.ssh_port, 
                username=self.exam.vm_username, 
                password=self.exam.vm_password,
                timeout=10
            )
            
            stdin, stdout, stderr = client.exec_command(command)
            output = stdout.read().decode() + stderr.read().decode()
            client.close()
            
            return output
        except (paramiko.AuthenticationException, socket.timeout, Exception) as e:
            raise Exception(f"SSH command execution failed: {str(e)}")

    def get_vm_status(self):
        from .vbox_manager import vbox_manager
        if not self.vm_name or self.vm_name == '':
            return "not_created"
            
        info = vbox_manager.get_vm_info(self.vm_name)
        return info.get("VMState", "unknown")


class PracticalExamResult(models.Model):
    session = models.OneToOneField(PracticalExamSession, on_delete=models.CASCADE)
    score = models.IntegerField(default=0)
    total_possible = models.IntegerField(default=100)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.session.student.username} - {self.session.exam.title} - {self.score}/{self.total_possible}"