from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import User
import secrets
from django.core.mail import send_mail

@receiver(post_save, sender=User)
def send_welcome_email(sender, instance, created, **kwargs):
    if created and instance.user_type == 'student':
        temp_password = secrets.token_urlsafe(8)
        instance.set_password(temp_password)
        instance.save()
        
        send_mail(
            'Your Exam Account',
            f'Username: {instance.username}\nPassword: {temp_password}\nLogin at: http://yourapp.com/login',
            'noreply@mcqapp.com',
            [instance.email],
            fail_silently=False,
        )