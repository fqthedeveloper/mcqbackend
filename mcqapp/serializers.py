from django.db import IntegrityError
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.crypto import get_random_string
from django.core.mail import send_mail

from mcqbackend import settings

from .models import (
    User, Subject, StudentSubjectEnrollment,
    Question, Exam, ExamSession, Answer, Result
)

User = get_user_model()

# ================= USER ================= #

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'user_type',
            'is_verified', 'is_active',
            'first_name', 'last_name'
        ]


class StudentCreateSerializer(serializers.ModelSerializer):
    subject_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'subject_ids'
        ]

    def create(self, validated_data):
        subject_ids = validated_data.pop('subject_ids', [])
        password = get_random_string(10)

        # 1️⃣ Create student
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data.get('username', validated_data['email']),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            user_type='student',
            password=password,
            force_password_change=True,
            is_active=True
        )

        # 2️⃣ Assign subjects
        for subject_id in subject_ids:
            StudentSubjectEnrollment.objects.update_or_create(
                student=user,
                subject_id=subject_id,
                defaults={'is_active': True}
            )

        # 3️⃣ Send credentials email
        send_mail(
            subject="Student Account Created",
            message=f"""
                Hello {user.first_name or user.username},

                Your account has been created.

                Email: {user.email}
                Password: {password}

                Login URL:
                http://localhost:3000/login

                You must change your password after first login.
                """,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return user

class StudentUpdateSerializer(serializers.ModelSerializer):
    subject_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'is_active',
            'subject_ids'
        ]

    def update(self, instance, validated_data):
        subject_ids = validated_data.pop('subject_ids', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if subject_ids is not None:
            # deactivate all
            StudentSubjectEnrollment.objects.filter(
                student=instance
            ).update(is_active=False)

            # activate selected
            for subject_id in subject_ids:
                StudentSubjectEnrollment.objects.update_or_create(
                    student=instance,
                    subject_id=subject_id,
                    defaults={'is_active': True}
                )

        return instance
    
    
class PasswordChangeSerializer(serializers.Serializer):
    new_password = serializers.CharField(validators=[validate_password])
    confirm_password = serializers.CharField()

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match")
        return data


# ================= SUBJECT ================= #

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name', 'description', 'is_active']


# ================= ENROLLMENT ================= #

class StudentSubjectEnrollmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentSubjectEnrollment
        fields = ['id', 'student', 'subject', 'is_active']


# ================= QUESTION ================= #

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = [
            'id', 'subject',
            'text',
            'option_a', 'option_b',
            'option_c', 'option_d',
            'correct_option', 'marks'
        ]


# ================= EXAM (MCQ ONLY) ================= #

class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exam
        fields = [
            'id', 'title', 'subject',
            'duration', 'mode',
            'is_published'
        ]


# ================= SESSION ================= #

class ExamSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamSession
        fields = [
            'id', 'student', 'exam',
            'start_time', 'end_time',
            'is_completed'
        ]


# ================= ANSWER ================= #

class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ['id', 'session', 'question', 'selected_answers']


# ================= RESULT ================= #

class ResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = Result
        fields = ['id', 'session', 'score', 'total_marks']
