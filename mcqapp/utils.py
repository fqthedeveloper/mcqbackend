# utils.py
import random
from django.core.mail import send_mail
from django.conf import settings


def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(email, otp):
    subject = "Your Login OTP"
    message = f"""
        Your OTP for login is: {otp}

        This OTP is valid for 10 minutes.
        If you did not request this, please ignore this email.
        """
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
