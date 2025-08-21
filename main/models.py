from asyncio.log import logger
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.conf import settings
import secrets
import time
import secrets
import subprocess
import time
from django.core.exceptions import ValidationError



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
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    duration = models.PositiveIntegerField(help_text="Duration in minutes")
    vm_base_name = models.CharField(
        max_length=255,
        default="Redhat",
        help_text="Base VM name to clone from"
    )
    vm_snapshot = models.CharField(
        max_length=255,
        default="base_snapshot",
        help_text="Snapshot to use for cloning"
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
    vm_username = models.CharField(
        max_length=100,
        default="examuser",
        help_text="Username to access the VM"
    )
    vm_password = models.CharField(
        max_length=100,
        default="exampass",
        help_text="Password to access the VM"
    )
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class PracticalExamSession(models.Model):
    STATUS_CHOICES = (
        ('starting', 'Starting'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('terminated', 'Terminated'),
        ('failed', 'Failed'),
    )
    
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    exam = models.ForeignKey('PracticalExam', on_delete=models.CASCADE)
    vm_name = models.CharField(max_length=255, null=True, blank=True)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='starting')
    verification_output = models.TextField(blank=True, null=True)
    is_success = models.BooleanField(default=False)
    termination_reason = models.TextField(null=True, blank=True)
    token = models.CharField(max_length=100, default=secrets.token_urlsafe, unique=True)
    startup_log = models.TextField(blank=True, null=True)
    ssh_port = models.IntegerField(null=True, blank=True, help_text="SSH port for VM access")

    class Meta:
        unique_together = [('student', 'exam')]
        ordering = ['-start_time']
        
    def __str__(self):
        return f"{self.student.username} - {self.exam.title} ({self.status})"
    
    def start_vm(self):
        """Create and start a VirtualBox VM for the exam session"""
        from .vbox_settings import vbox_manager
        log_lines = []
        
        try:
            # Generate unique VM name
            self.vm_name = f"exam-{self.exam.id}-{self.student.id}-{secrets.token_hex(4)}"
            log_lines.append(f"Generated VM name: {self.vm_name}")
            
            # Clone the base VM
            log_lines.append(f"Cloning VM from {self.exam.vm_base_name} with snapshot {self.exam.vm_snapshot}")
            if not vbox_manager.clone_vm(self.vm_name, self.exam.vm_snapshot):
                raise Exception("Failed to clone VM")
            
            # Configure network
            log_lines.append("Configuring NAT network")
            if not vbox_manager.set_network_nat(self.vm_name):
                raise Exception("Failed to configure network")
            
            # Start the VM
            log_lines.append("Starting VM")
            if not vbox_manager.start_vm(self.vm_name, headless=True):
                raise Exception("Failed to start VM")
            
            # Wait for VM to boot
            log_lines.append("Waiting for VM to boot")
            vbox_manager.wait_for_vm_boot(self.vm_name)
            log_lines.append("VM is ready")
            
            # Execute setup command if defined
            if self.exam.setup_command:
                log_lines.append(f"Executing setup command: {self.exam.setup_command}")
                output = vbox_manager.execute_command_in_vm(
                    self.vm_name, 
                    self.exam.setup_command,
                    self.exam.vm_username,
                    self.exam.vm_password
                )
                log_lines.append(f"Setup command output: {output}")
                
            # Update session status
            self.status = 'running'
            self.save()
            log_lines.append("VM started successfully")
            
        except Exception as e:
            error_msg = f"VM startup failed: {str(e)}"
            log_lines.append(error_msg)
            self.status = 'failed'
            self.termination_reason = error_msg
            logger.error(error_msg)
            
            # Clean up on failure
            if self.vm_name:
                try:
                    vbox_manager.delete_vm(self.vm_name)
                except:
                    pass
        finally:
            self.startup_log = "\n".join(log_lines)
            self.save()
    
    def terminate_vm(self):
        """Terminate and delete the VM"""
        if not self.vm_name:
            return
            
        try:
            from .vbox_settings import vbox_manager
            vbox_manager.delete_vm(self.vm_name)
            self.vm_name = None
            self.save()
            logger.info(f"VM terminated: {self.vm_name}")
        except Exception as e:
            logger.error(f"VM termination failed: {str(e)}")
            raise Exception(f"Failed to clean up exam environment: {str(e)}")
    
    def execute_command(self, command):
        """Execute a command in the VM"""
        if not self.vm_name:
            return "No active VM"
            
        try:
            from .vbox_settings import vbox_manager
            output = vbox_manager.execute_command_in_vm(
                self.vm_name, 
                command,
                self.exam.vm_username,
                self.exam.vm_password
            )
            return output
        except Exception as e:
            return f"Command execution failed: {str(e)}"
    
    def get_vm_status(self):
        """Get the status of the VM"""
        if not self.vm_name:
            return 'not created'
            
        try:
            from .vbox_settings import vbox_manager
            info = vbox_manager.get_vm_info(self.vm_name)
            return info.get('VMState', 'unknown')
        except Exception as e:
            logger.error(f"VM status error: {str(e)}")
            return 'error'

    def save(self, *args, **kwargs):
        if self.status in ['completed', 'terminated'] and self.vm_name:
            self.terminate_vm()
        super().save(*args, **kwargs)

class PracticalExamResult(models.Model):
    session = models.ForeignKey(PracticalExamSession, on_delete=models.CASCADE)
    score = models.FloatField()
    total_possible = models.FloatField()
    details = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Result for {self.session}"