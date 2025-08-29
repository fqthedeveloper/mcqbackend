from rest_framework import serializers
from .models import *
from django.contrib.auth import get_user_model
import logging
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.conf import settings
import logging
import secrets
import string
from django.db import IntegrityError, models
from django.conf import settings
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from .models import Subject
from .permissions import IsAdminUserOnly



logger = logging.getLogger(__name__)
User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    last_login = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S', read_only=True)
    date_joined = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'user_type', 'is_verified',
                  'last_login', 'date_joined', 'is_active', 'subjects']

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


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name']


class AddSubjectSerializer(serializers.Serializer):
    subject_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True
    )

    def validate_subject_ids(self, value):
        if not value:
            raise serializers.ValidationError("At least one subject must be selected")
        return value


class StudentSubjectSerializer(serializers.ModelSerializer):
    subjects = SubjectSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'subjects']


class StudentCreateSerializer(serializers.ModelSerializer):
    subjects = SubjectSerializer(many=True, required=False, read_only=True)
    subject_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'password', 'subjects', 'subject_ids', 'is_verified', 'is_active']
        extra_kwargs = {
            'user_type': {'read_only': True}
        }

    def generate_random_password(self, length=12):
        """Generate a secure random password"""
        alphabet = string.ascii_letters + string.digits + string.punctuation
        return ''.join(secrets.choice(alphabet) for i in range(length))

    def send_credentials_email(self, user, password, subject="IRT Exam Portal Account Credentials"):
        """Helper method to send credentials email"""
        try:
            send_mail(
                subject=subject,
                message=f'''
                Hello {user.first_name},
                
                Your student account has been created/updated.
                
                Username: {user.email}
                Password: {password}
                
                Please change your password after first login.
                
                Best regards,
                IRT Technalogeis 
                ''',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            logger.info(f"Credentials email sent to {user.email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {user.email}: {str(e)}")
            return False

    def create(self, validated_data):
        subject_ids = validated_data.pop('subject_ids', [])
        password = validated_data.pop('password', None)
        
        if password is None:
            password = self.generate_random_password()
            
        # Create user with the custom manager
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data.get('username', validated_data['email']),
            password=password,
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            user_type='student',
            is_verified=validated_data.get('is_verified', False),
            is_active=validated_data.get('is_active', True)
        )
        
        # Add subjects to student
        if subject_ids:
            subjects = Subject.objects.filter(id__in=subject_ids)
            user.subjects.set(subjects)
            
        # Send email with credentials
        self.send_credentials_email(user, password)
        
        return user

    def update(self, instance, validated_data):
        subject_ids = validated_data.pop('subject_ids', None)
        password = validated_data.pop('password', None)
        email_changed = 'email' in validated_data and instance.email != validated_data['email']
        
        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        if password:
            instance.set_password(password)
            
        instance.save()
        
        # Update subjects if provided
        if subject_ids is not None:
            subjects = Subject.objects.filter(id__in=subject_ids)
            instance.subjects.set(subjects)
            
        # Send email if password was changed or email was updated
        if password:
            self.send_credentials_email(instance, password, "Your Password Has Been Updated")
        elif email_changed:
            try:
                send_mail(
                    subject='Your email has been updated',
                    message=(
                        f'Hello {instance.first_name},\n\n'
                        f'Your email address has been changed to {instance.email}.\n'
                        'If you did not request this change, please contact support immediately.'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[instance.email],
                    fail_silently=False,
                )
                logger.info(f"Email change notification sent to {instance.email}")
            except Exception as e:
                logger.error(f"Failed to send email change notification to {instance.email}: {str(e)}")
            
        return instance


class StudentViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(user_type='student')
    serializer_class = StudentCreateSerializer
    permission_classes = [IsAuthenticated, IsAdminUserOnly]
    authentication_classes = [TokenAuthentication]

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            self.perform_create(serializer)
        except IntegrityError:
            return Response(
                {"detail": "A user with this email or username already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['POST'])
    def add_subjects(self, request, pk=None):
        student = self.get_object()
        serializer = AddSubjectSerializer(data=request.data)
        
        if serializer.is_valid():
            subject_ids = serializer.validated_data['subject_ids']
            subjects = Subject.objects.filter(id__in=subject_ids)
            student.subjects.add(*subjects)
            
            return Response(
                {"detail": "Subjects added successfully."},
                status=status.HTTP_200_OK
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['POST'])
    def remove_subjects(self, request, pk=None):
        student = self.get_object()
        serializer = AddSubjectSerializer(data=request.data)
        
        if serializer.is_valid():
            subject_ids = serializer.validated_data['subject_ids']
            subjects = Subject.objects.filter(id__in=subject_ids)
            student.subjects.remove(*subjects)
            
            return Response(
                {"detail": "Subjects removed successfully."},
                status=status.HTTP_200_OK
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordChangeSerializer(serializers.Serializer):
    new_password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    confirm_password = serializers.CharField(write_only=True, required=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data



        
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
    exam = ExamSerializer(read_only=True)  
    exam_title = serializers.CharField(source='exam.title', read_only=True)
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)

    class Meta:
        model = ExamSession
        fields = '__all__'
        depth = 1

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
    exam = serializers.PrimaryKeyRelatedField(queryset=PracticalExam.objects.all())
    student = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = PracticalExamSession
        fields = [
            'id', 'student', 'exam', 'vm_name', 'ssh_port', 'token', 'status',
            'start_time', 'end_time', 'startup_log', 'verification_output',
            'is_success', 'termination_reason'
        ]
        read_only_fields = ['vm_name', 'ssh_port', 'token', 'status', 'start_time', 'end_time', 'startup_log', 'verification_output', 'is_success', 'termination_reason']

class PracticalExamResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = PracticalExamResult
        fields = '__all__'
    
    def get_session_info(self, obj):
        return {
            'start_time': obj.session.start_time,
            'end_time': obj.session.end_time,
            'duration': (obj.session.end_time - obj.session.start_time).total_seconds() if obj.session.end_time else None
        }
    

class StudentExamSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    can_take = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = ['id', 'title', 'subject', 'subject_name', 'mode', 'duration', 
                 'start_time', 'end_time', 'is_published', 'question_count', 'can_take']

    def get_can_take(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Check if student has this subject
            if obj.subject not in request.user.subjects.all():
                return False
            
            # Check if exam is published and within time range
            if not obj.is_published:
                return False
                
            now = timezone.now()
            if obj.start_time and now < obj.start_time:
                return False
            if obj.end_time and now > obj.end_time:
                return False
                
            # Check if already completed (for strict mode)
            if obj.mode == 'strict':
                completed = ExamSession.objects.filter(
                    student=request.user, 
                    exam=obj, 
                    is_completed=True
                ).exists()
                if completed:
                    return False
                    
            return True
        return False