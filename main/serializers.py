from rest_framework import serializers
from .models import *
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
import logging
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.utils.crypto import get_random_string

logger = logging.getLogger(__name__)
User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    last_login = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S', read_only=True)
    date_joined = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S', read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'user_type', 'is_verified', 
                  'last_login', 'date_joined', 'is_active']

class LoginSerializer(serializers.Serializer):
    username_or_email = serializers.CharField()
    password = serializers.CharField()

    def validate(self, data):
        username_or_email = data.get("username_or_email")
        password = data.get("password")

        if not username_or_email or not password:
            raise serializers.ValidationError(
                "Both username/email and password are required.",
                code='authorization'
            )

        user = None
        error_msg = "Invalid credentials"
        
        try:
            # Try email lookup first
            if '@' in username_or_email:
                user = User.objects.get(email=username_or_email)
            else:
                user = User.objects.get(username=username_or_email)
        except User.DoesNotExist:
            logger.warning(f"Login attempt for non-existent user: {username_or_email}")
            raise serializers.ValidationError(error_msg, code='authorization')
        except User.MultipleObjectsReturned:
            logger.error(f"Multiple users found for: {username_or_email}")
            # Try to get the first active user
            users = User.objects.filter(
                models.Q(email=username_or_email) | 
                models.Q(username=username_or_email)
            ).filter(is_active=True)
            
            if users.exists():
                user = users.first()
            else:
                raise serializers.ValidationError(
                    "Authentication error. Please contact support.",
                    code='authorization'
                )

        # Validate credentials
        if not user.check_password(password):
            logger.warning(f"Invalid password for user: {user.email}")
            raise serializers.ValidationError(error_msg, code='authorization')
        
        if not user.is_active:
            logger.warning(f"Login attempt for inactive user: {user.email}")
            raise serializers.ValidationError(
                "User account is disabled", 
                code='authorization'
            )
        
        data['user'] = user
        return data
    

class StudentCreateSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name']

    def create(self, validated_data):
        password = get_random_string(length=10)
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data.get('username', validated_data['email']),
            user_type='student',
            password=password,
            force_password_change=True,
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
        )

        send_mail(
            subject='Your IRT MCQ Webapp Student Account Login',
            message=(
                f'Your IRT MCQ Webapp account has been created.\n\n'
                f'Email: {user.email}\n'
                f'Password: {password}\n\n'
                'Please change your password after first login.'
            ),
            from_email='no-reply@example.com',
            recipient_list=[user.email],
            fail_silently=False,
        )
        return user


class PasswordChangeSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, required=True, validators=[validate_password])


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name']

class QuestionSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(read_only=True)  # Nested subject info

    class Meta:
        model = Question
        fields = ['id', 'subject', 'text', 'options', 'correct_answers', 'marks', 'is_multi']
        

    def validate_exam(self, value):
        # Ensure the exam exists - this is automatic by FK, but you can add extra checks here if needed
        if not Exam.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("Exam does not exist")
        return value

class ExamQuestionSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='question.id')
    text = serializers.ReadOnlyField(source='question.text')
    marks = serializers.ReadOnlyField(source='question.marks')
    is_multi = serializers.ReadOnlyField(source='question.is_multi')
    options = serializers.ReadOnlyField(source='question.options')

    class Meta:
        model = ExamQuestion
        fields = ['id', 'text', 'marks', 'is_multi', 'options', 'order']


class ExamSerializer(serializers.ModelSerializer):
    questions = ExamQuestionSerializer(source='examquestion_set', many=True, read_only=True)
    selected_questions = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )
    subject_name = serializers.CharField(source='subject.name', read_only=True)

    created_at = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S', read_only=True)
    updated_at = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S', read_only=True)
    
    class Meta:
        model = Exam
        fields = [
            'id', 'title', 'subject', 'subject_name', 'mode', 'duration', 
            'start_time', 'end_time', 'is_published', 'created_at', 'updated_at',
            'questions', 'selected_questions'
        ]
        extra_kwargs = {
            'subject': {'required': True},
            'mode': {'required': True},
            'duration': {'required': True},
        }

    def create(self, validated_data):
        selected_questions = validated_data.pop('selected_questions', [])
        exam = Exam.objects.create(**validated_data)
        for order, question_id in enumerate(selected_questions):
            try:
                question = Question.objects.get(id=question_id)
                ExamQuestion.objects.create(exam=exam, question=question, order=order)
            except Question.DoesNotExist:
                pass
        return exam

    def update(self, instance, validated_data):
        selected_questions = validated_data.pop('selected_questions', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if selected_questions is not None:
            instance.examquestion_set.all().delete()
            for order, question_id in enumerate(selected_questions):
                try:
                    question = Question.objects.get(id=question_id)
                    ExamQuestion.objects.create(exam=instance, question=question, order=order)
                except Question.DoesNotExist:
                    pass
        return instance

class ExamSessionSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source='exam.title', read_only=True)
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    
    class Meta:
        model = ExamSession
        fields = '__all__'
        read_only_fields = ['start_time', 'end_time', 'is_completed']

class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = '__all__'

class ResultSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source='session.exam.title', read_only=True)
    student_name = serializers.CharField(source='session.student.get_full_name', read_only=True)
    
    class Meta:
        model = Result
        fields = '__all__'