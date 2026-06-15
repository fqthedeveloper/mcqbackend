from django.db import models
from django.conf import settings
from django.utils import timezone
from ckeditor.fields import RichTextField

from mcqapp.models import Subject

User = settings.AUTH_USER_MODEL


# =========================================================
# MACHINE TEMPLATE
# =========================================================

class CyberMachineTemplate(models.Model):

    ROLE_CHOICES = (
        ('attacker', 'Attacker'),
        ('victim', 'Victim'),
        ('monitor', 'Monitor'),
    )
    OS_CHOICES = (
        ('linux', 'Linux'),
        ('windows', 'Windows'),
    )

    name = models.CharField(
        max_length=200,
        unique=True
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES
    )

    base_box = models.CharField(
        max_length=255
    )

    memory_mb = models.IntegerField(
        default=2048
    )

    cpu_count = models.IntegerField(
        default=2
    )

    gui_enabled = models.BooleanField(
        default=True
    )

    description = models.TextField(
        blank=True,
        null=True
    )


    os_type = models.CharField(
        max_length=50,
        choices=OS_CHOICES,
        default='linux'
    )

    default_username = models.CharField(
        max_length=100,
        default='vagrant'
    )

    default_password = models.CharField(
        max_length=100,
        default='vagrant'
    )

    extra_disk_gb = models.IntegerField(
        default=0
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )
    

    def __str__(self):
        return self.name


# =========================================================
# TOPOLOGY
# =========================================================

class CyberTopology(models.Model):

    name = models.CharField(
        max_length=200,
        unique=True
    )

    description = models.TextField(
        blank=True,
        null=True
    )

    attacker_template = models.ForeignKey(
        CyberMachineTemplate,
        on_delete=models.CASCADE,
        related_name='attacker_topologies'
    )

    victim_template = models.ForeignKey(
        CyberMachineTemplate,
        on_delete=models.CASCADE,
        related_name='victim_topologies'
    )

    monitor_template = models.ForeignKey(
        CyberMachineTemplate,
        on_delete=models.SET_NULL,
        related_name='monitor_topologies',
        null=True,
        blank=True
    )

    network_name = models.CharField(
        max_length=200,
        default='cyberlab-net'
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.name


# =========================================================
# PRACTICAL TASK
# =========================================================

class CyberPracticalTask(models.Model):

    DIFFICULTY_CHOICES = (
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    )

    title = models.CharField(
        max_length=255,
        unique=True
    )

    description = RichTextField()

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='cyber_practical_tasks'
    )

    topology = models.ForeignKey(
        CyberTopology,
        on_delete=models.CASCADE,
        related_name='tasks'
    )

    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default='easy'
    )

    duration_minutes = models.IntegerField(
        default=60
    )

    total_marks = models.IntegerField(
        default=100
    )

    variable_schema = models.JSONField(
        default=dict,
        blank=True
    )

    attacker_init_template = models.TextField()

    victim_init_template = models.TextField()

    monitor_init_template = models.TextField(
        blank=True,
        null=True
    )

    verify_template = models.TextField()

    is_published = models.BooleanField(
        default=False
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def save(self, *args, **kwargs):

        if self.attacker_init_template:
            self.attacker_init_template = (
                self.attacker_init_template
                .replace('\r\n', '\n')
                .strip() + '\n'
            )

        if self.victim_init_template:
            self.victim_init_template = (
                self.victim_init_template
                .replace('\r\n', '\n')
                .strip() + '\n'
            )

        if self.monitor_init_template:
            self.monitor_init_template = (
                self.monitor_init_template
                .replace('\r\n', '\n')
                .strip() + '\n'
            )

        if self.verify_template:
            self.verify_template = (
                self.verify_template
                .replace('\r\n', '\n')
                .strip() + '\n'
            )

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


# =========================================================
# CYBER SESSION
# =========================================================

class CyberSession(models.Model):

    STATUS_CHOICES = (
        ('starting', 'Starting'),
        ('running', 'Running'),
        ('submitted', 'Submitted'),
        ('expired', 'Expired'),
        ('terminated', 'Terminated'),
        ('failed', 'Failed'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='cyber_sessions'
    )

    task = models.ForeignKey(
        CyberPracticalTask,
        on_delete=models.CASCADE,
        related_name='sessions'
    )

    variables = models.JSONField(
        default=dict,
        blank=True
    )

    obtained_marks = models.IntegerField(
        default=0
    )

    percentage = models.FloatField(
        default=0.0
    )

    verification_output = models.TextField(
        blank=True,
        null=True
    )

    verification_details = models.JSONField(
        blank=True,
        null=True
    )

    is_passed = models.BooleanField(
        default=False
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='starting',
        db_index=True
    )

    history_path = models.CharField(
        max_length=500,
        blank=True,
        null=True
    )

    start_time = models.DateTimeField(
        default=timezone.now
    )

    end_time = models.DateTimeField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ['-id']

    def calculate_percentage(self):

        if self.task.total_marks > 0:

            self.percentage = round(
                (
                    self.obtained_marks /
                    self.task.total_marks
                ) * 100,
                2
            )

        else:
            self.percentage = 0.0

    def __str__(self):
        return f'{self.user} | {self.task.title}'


# =========================================================
# MACHINE SESSION
# =========================================================

class CyberMachineSession(models.Model):

    ROLE_CHOICES = (
        ('attacker', 'Attacker'),
        ('victim', 'Victim'),
        ('monitor', 'Monitor'),
    )

    STATUS_CHOICES = (
        ('starting', 'Starting'),
        ('running', 'Running'),
        ('failed', 'Failed'),
        ('destroyed', 'Destroyed'),
    )

    session = models.ForeignKey(
        CyberSession,
        on_delete=models.CASCADE,
        related_name='machines'
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES
    )

    template = models.ForeignKey(
        CyberMachineTemplate,
        on_delete=models.CASCADE
    )

    vm_name = models.CharField(
        max_length=255
    )

    vm_ip = models.GenericIPAddressField(
        null=True,
        blank=True
    )

    guacamole_connection_id = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    guacamole_url = models.TextField(
        blank=True,
        null=True
    )

    generated_username = models.CharField(
        max_length=100
    )

    generated_password = models.CharField(
        max_length=255
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='starting'
    )

    recording_path = models.CharField(
        max_length=500,
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f'{self.session.id} | {self.role}'
    

class HypervisorNode(models.Model):

    NODE_CHOICES = (
        ('vagrant', 'Vagrant'),
        ('proxmox', 'Proxmox'),
    )

    name = models.CharField(
        max_length=255
    )

    node_type = models.CharField(
        max_length=50,
        choices=NODE_CHOICES,
        default='vagrant'
    )

    host = models.CharField(
        max_length=255
    )

    username = models.CharField(
        max_length=255
    )

    password = models.CharField(
        max_length=255
    )

    max_students = models.IntegerField(
        default=50
    )

    current_students = models.IntegerField(
        default=0
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return self.name


class CyberEventLog(models.Model):

    EVENT_TYPES = (
        ('start', 'Start'),
        ('stop', 'Stop'),
        ('verify', 'Verify'),
        ('attack', 'Attack'),
        ('defense', 'Defense'),
    )

    session = models.ForeignKey(
        CyberSession,
        on_delete=models.CASCADE
    )

    machine = models.ForeignKey(
        CyberMachineSession,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    event_type = models.CharField(
        max_length=100,
        choices=EVENT_TYPES
    )

    data = models.JSONField(
        default=dict
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )