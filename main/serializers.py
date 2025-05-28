from rest_framework import serializers
from .models import *
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
import logging

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
    

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = '__all__'

class ExamQuestionSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='question.id')
    text = serializers.ReadOnlyField(source='question.text')
    marks = serializers.ReadOnlyField(source='question.marks')
    is_multi = serializers.ReadOnlyField(source='question.is_multi')

    class Meta:
        model = ExamQuestion
        fields = ['id', 'text', 'marks', 'is_multi', 'order']

class ExamSerializer(serializers.ModelSerializer):
    questions = ExamQuestionSerializer(source='examquestion_set', many=True, read_only=True)
    selected_questions = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = Exam
        fields = '__all__'
        extra_kwargs = {
            'subject': {'required': True},
            'mode': {'required': True},
            'duration': {'required': True},
        }

    def create(self, validated_data):
        selected_questions = validated_data.pop('selected_questions', [])
        exam = Exam.objects.create(**validated_data)
        
        # Add selected questions to exam
        for order, question_id in enumerate(selected_questions):
            try:
                question = Question.objects.get(id=question_id)
                ExamQuestion.objects.create(
                    exam=exam, 
                    question=question, 
                    order=order
                )
            except Question.DoesNotExist:
                pass
                
        return exam

    def update(self, instance, validated_data):
        selected_questions = validated_data.pop('selected_questions', None)
        
        # Update exam fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update questions if provided
        if selected_questions is not None:
            # Clear existing questions
            instance.examquestion_set.all().delete()
            
            # Add new selected questions
            for order, question_id in enumerate(selected_questions):
                try:
                    question = Question.objects.get(id=question_id)
                    ExamQuestion.objects.create(
                        exam=instance, 
                        question=question, 
                        order=order
                    )
                except Question.DoesNotExist:
                    pass
                    
        return instance

class ExamSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamSession
        fields = '__all__'

class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = '__all__'

class ResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = Result
        fields = '__all__'