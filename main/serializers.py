from django.conf import settings
from django.db import IntegrityError
from rest_framework import serializers
from .models import *
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
import logging
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from rest_framework import status
from rest_framework.response import Response



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
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'is_verified', 'force_password_change']

    def create(self, validated_data):
        password = get_random_string(length=10)
        try:
            user = User.objects.create_user(
                email=validated_data['email'],
                username=validated_data.get('username', validated_data['email']),
                user_type='student',
                password=password,
                force_password_change=True,
                first_name=validated_data['first_name'],
                last_name=validated_data['last_name'],
            )
        except IntegrityError as e:
            # This handles database unique constraints like duplicate email or username
            raise serializers.ValidationError({"detail": "A user with this email or username already exists."})

        send_mail(
            subject='Your IRT MCQ Webapp Student Account Login',
            message=(
                f'Your IRT MCQ Webapp account has been created.\n\n'
                f'Email: {user.email}\n'
                f'Password: {password}\n\n'
                'Please change your password after first login.'
            ),
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return user

class PasswordChangeSerializer(serializers.Serializer):
    new_password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    confirm_password = serializers.CharField(write_only=True, required=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name']


class QuestionSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()
    subject = serializers.StringRelatedField(read_only=True)
    subject_id = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.all(),
        source='subject',  # maps to ForeignKey field
        write_only=True
    )

    class Meta:
        model = Question
        fields = [
            'id', 'subject', 'subject_id', 'text', 'is_multi', 'marks',
            'option_a', 'option_b', 'option_c', 'option_d',
            'options', 'correct_option', 'explanation'
        ]

    def get_options(self, obj):
        return {
            "A": obj.option_a,
            "B": obj.option_b,
            "C": obj.option_c,
            "D": obj.option_d
        }

    def to_internal_value(self, data):
        internal_value = super().to_internal_value(data)

        # Parse options dictionary
        if 'options' in data:
            options = data['options']
            if isinstance(options, dict):
                internal_value['option_a'] = options.get('A', '')
                internal_value['option_b'] = options.get('B', '')
                internal_value['option_c'] = options.get('C', '')
                internal_value['option_d'] = options.get('D', '')

        # Handle correct answer
        if 'correct_answers' in data:
            correct_answers = data['correct_answers']
            is_multi = internal_value.get('is_multi', False)

            if is_multi:
                if isinstance(correct_answers, list):
                    internal_value['correct_option'] = ','.join(correct_answers)
            else:
                if isinstance(correct_answers, str):
                    internal_value['correct_option'] = correct_answers

        return internal_value

    def validate(self, data):
        correct_option = data.get('correct_option', '')
        is_multi = data.get('is_multi', False)

        if is_multi:
            if not all(opt in ['A', 'B', 'C', 'D'] for opt in correct_option.split(',')):
                raise serializers.ValidationError({
                    'correct_answers': 'Invalid multi-answer format. Use comma-separated A,B,C,D.'
                })
        else:
            if correct_option not in ['A', 'B', 'C', 'D']:
                raise serializers.ValidationError({
                    'correct_answers': 'Answer must be one of A, B, C, or D.'
                })

        return data


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = '__all__'


class ExamQuestionSerializer(serializers.ModelSerializer):
    question = QuestionSerializer(read_only=True)

    class Meta:
        model = ExamQuestion
        fields = ['id', 'question', 'order']


class ExamSerializer(serializers.ModelSerializer):
    questions = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    created_at = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S', read_only=True)
    updated_at = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S', read_only=True)
    question_count = serializers.IntegerField(read_only=True)
    practical_count = serializers.SerializerMethodField()
    
    selected_questions = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        default=[]
    )
    
    selected_practical_exams = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        default=[]
    )

    class Meta:
        model = Exam
        fields = [
            'id', 'title', 'subject', 'subject_name', 'mode', 'duration',
            'start_time', 'end_time', 'is_published', 'created_at', 'updated_at',
            'questions', 'question_count', 'practical_count', 
            'selected_questions', 'selected_practical_exams'
        ]

    def get_questions(self, obj):
        return ExamQuestionSerializer(
            obj.examquestion_set.all().order_by('order'), 
            many=True
        ).data

    def get_practical_count(self, obj):
        return obj.practical_exams.count() if obj.mode == 'practical' else 0

    def create(self, validated_data):
        selected_questions = validated_data.pop('selected_questions', [])
        selected_practical_exams = validated_data.pop('selected_practical_exams', [])
        exam = Exam.objects.create(**validated_data)
        
        self._process_questions(exam, selected_questions)
        exam.practical_exams.set(selected_practical_exams)
        
        return exam

    def update(self, instance, validated_data):
        selected_questions = validated_data.pop('selected_questions', None)
        selected_practical_exams = validated_data.pop('selected_practical_exams', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if selected_questions is not None:
            instance.examquestion_set.all().delete()
            self._process_questions(instance, selected_questions)
        
        if selected_practical_exams is not None:
            instance.practical_exams.set(selected_practical_exams)
        
        return instance

    def _process_questions(self, exam, question_ids):
        for order, question_id in enumerate(question_ids):
            try:
                question = Question.objects.get(id=question_id)
                ExamQuestion.objects.create(exam=exam, question=question, order=order)
            except Question.DoesNotExist:
                continue


class ExamSessionSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source='exam.title', read_only=True)
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)

    class Meta:
        model = ExamSession
        fields = '__all__'
        read_only_fields = ['start_time', 'end_time', 'is_completed', 'termination_reason']

class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = '__all__'


class ResultSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source='session.exam.title', read_only=True)
    student_name = serializers.CharField(source='session.student.get_full_name', read_only=True)
    termination_reason = serializers.CharField(source='session.termination_reason', read_only=True)

    class Meta:
        model = Result
        fields = '__all__'


class PracticalExamSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)    
    
    class Meta:
        model = PracticalExam
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class PracticalExamSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PracticalExamSession
        fields = '__all__'
        extra_kwargs = {
            'student': {'required': False},
            'token': {'read_only': True},
            'container_id': {'read_only': True},
            'start_time': {'read_only': True},
            'end_time': {'read_only': True},
            'status': {'read_only': True},
            'verification_output': {'read_only': True},
            'is_success': {'read_only': True},
            'termination_reason': {'read_only': True},
        }


class PracticalExamResultSerializer(serializers.ModelSerializer):
    session_info = serializers.SerializerMethodField()
    exam_title = serializers.CharField(source='session.exam.title', read_only=True)
    student_name = serializers.CharField(source='session.student.username', read_only=True)
    
    class Meta:
        model = PracticalExamResult
        fields = '__all__'
    
    def get_session_info(self, obj):
        return {
            'start_time': obj.session.start_time,
            'end_time': obj.session.end_time,
            'duration': (obj.session.end_time - obj.session.start_time).total_seconds() if obj.session.end_time else None
        }