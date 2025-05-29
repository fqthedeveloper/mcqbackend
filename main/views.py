from rest_framework import viewsets, status, filters, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from .models import *
from .serializers import *
from .utils import process_excel
from django.utils import timezone
from django.http import HttpResponse
import pandas as pd
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.authtoken.models import Token
from django.db import IntegrityError
from django.db import IntegrityError, transaction
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.permissions import IsAuthenticated
from .permissions import IsAdminUserOnly
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
import json



User = get_user_model()

logger = logging.getLogger(__name__)
User = get_user_model()

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        user = serializer.validated_data['user']
        
        # Token creation with robust error handling
        token = None
        try:
            # First try to get existing token
            token = Token.objects.get(user=user)
        except Token.DoesNotExist:
            # If token doesn't exist, create a new one
            try:
                # Use atomic transaction to prevent partial creation
                with transaction.atomic():
                    token = Token.objects.create(user=user)
            except IntegrityError as e:
                logger.error(f"Token creation IntegrityError: {str(e)}")
                
                # Check if user was deleted during the process
                if not User.objects.filter(pk=user.pk).exists():
                    return Response(
                        {"error": "User account no longer exists"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Token might have been created by concurrent request
                try:
                    token = Token.objects.get(user=user)
                except Token.DoesNotExist:
                    logger.critical(f"Token missing after creation attempt: {user.id}")
                    # Attempt to create token with forced save
                    try:
                        token = Token(user=user)
                        token.save(force_insert=True)
                        logger.info(f"Successfully created token for user {user.id} with forced save")
                    except Exception as save_error:
                        logger.exception(f"Forced token creation failed: {str(save_error)}")
                        return Response(
                            {"error": "Authentication system error. Please contact support."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
            except Exception as e:
                logger.exception(f"Token creation failed: {str(e)}")
                return Response(
                    {"error": "Authentication service unavailable. Please try again."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

        # Successful authentication
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.user_type,
            'token': token.key,
            'force_password_change': user.force_password_change,
            'first_name': user.first_name,
            'is_verified': user.is_verified
        }, status=status.HTTP_200_OK)
    

class StudentViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(user_type='student')
    serializer_class = StudentCreateSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUserOnly]
    authentication_classes = [TokenAuthentication]

class ForcePasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        if serializer.is_valid():
            request.user.set_password(serializer.validated_data['new_password'])
            request.user.force_password_change = False
            request.user.save()
            return Response({"message": "Password changed successfully."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer


class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer  # Your serializer here
    
    
    @action(detail=False, methods=['GET'])
    def download_format(self, request):
        # Sample data with all required columns
        data = {
            'Subject': ['Mathematics', 'Science'],
            'Question': ['What is 2+2?', 'Water boils at?'],
            'Option A': ['3', '90°C'],
            'Option B': ['4', '100°C'],
            'Option C': ['5', '110°C'],
            'Option D': ['6', '120°C'],
            'Correct Answers': ['B', 'B'],  # Note the plural 'Answers' here
            'Marks': [1, 1],
            'Is Multi': [False, False]  # Boolean to indicate if multiple correct answers allowed
        }
        df = pd.DataFrame(data)
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="question_format.xlsx"'
        df.to_excel(response, index=False)
        return response

    @action(detail=False, methods=['POST'])
    def bulk_upload(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'status': 'error', 'message': 'No file uploaded'}, status=400)

        required_columns = [
            'Subject', 'Question', 'Option A', 'Option B', 'Option C', 'Option D',
            'Correct Answers', 'Marks', 'Is Multi'
        ]

        try:
            df = pd.read_excel(file)
        except Exception as e:
            return Response({'status': 'error', 'message': f'Failed to read Excel file: {str(e)}'}, status=400)

        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            return Response({
                'status': 'error',
                'message': f'Excel file is missing required columns: {", ".join(missing_cols)}'
            }, status=400)

        try:
            with transaction.atomic():
                for _, row in df.iterrows():
                    subject_obj, _ = Subject.objects.get_or_create(name=row['Subject'])

                    options = {
                        'A': row['Option A'],
                        'B': row['Option B'],
                        'C': row['Option C'],
                        'D': row['Option D'],
                    }

                    correct_answers = str(row['Correct Answers']).replace(' ', '').upper()

                    is_multi_val = row['Is Multi']
                    if isinstance(is_multi_val, str):
                        is_multi = is_multi_val.strip().lower() in ['true', '1', 'yes']
                    else:
                        is_multi = bool(is_multi_val)

                    # Convert options dict to JSON string if needed
                    import json
                    options_json = json.dumps(options)

                    Question.objects.create(
                        subject=subject_obj,
                        text=row['Question'],
                        options=options_json,  # use options_json if your field is TextField
                        correct_answers=correct_answers,
                        marks=int(row['Marks']),
                        is_multi=is_multi,
                    )
            return Response({'status': 'success', 'message': 'Questions uploaded successfully'})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=400)

class ExamViewSet(viewsets.ModelViewSet):
    queryset = Exam.objects.all()
    serializer_class = ExamSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        # For students, only show published exams
        if self.request.user.is_authenticated and self.request.user.user_type == 'student':
            return queryset.filter(is_published=True)
        return queryset
    
    @action(detail=True, methods=['POST'])
    def publish(self, request, pk=None):
        exam = self.get_object()
        exam.is_published = True
        exam.save()
        
        # Send email notifications to students
        students = User.objects.filter(user_type='student', is_active=True)
        notification_message = request.data.get(
            'message', 
            f'A new exam "{exam.title}" has been scheduled. Please check your dashboard for details.'
        )
        
        for student in students:
            send_mail(
                subject=f"New Exam: {exam.title}",
                message=notification_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[student.email],
                fail_silently=True,
            )
        
        return Response({'status': 'published', 'recipients': students.count()})
    
    @action(detail=True, methods=['POST'])
    def unpublish(self, request, pk=None):
        exam = self.get_object()
        exam.is_published = False
        exam.save()
        return Response({'status': 'unpublished'})


class ExamSessionViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSessionSerializer
    
    def get_queryset(self):
        queryset = ExamSession.objects.all()
        user = self.request.user
        
        if user.is_authenticated:
            if user.user_type == 'student':
                return queryset.filter(student=user)
            elif user.user_type == 'teacher':
                # Teachers can see sessions for their exams
                return queryset.filter(exam__subject__teacher=user)
        return queryset
    
    @action(detail=True, methods=['POST'])
    def start_exam(self, request, pk=None):
        session = self.get_object()
        if not session.start_time:
            session.start_time = timezone.now()
            session.save()
        return Response({'status': 'exam started'})
    
    @action(detail=True, methods=['POST'])
    def submit_exam(self, request, pk=None):
        session = self.get_object()
        
        if session.is_completed:
            return Response(
                {'error': 'Exam already submitted'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Calculate score
        answers = Answer.objects.filter(session=session)
        total_marks = 0
        score = 0
        details = {}
        
        for answer in answers:
            question = answer.question
            total_marks += question.marks
            
            # Get correct and selected answers
            correct_answers = set(question.correct_answers.split(','))
            selected_answers = set(answer.selected_answers.split(','))
            
            # Calculate question result
            is_correct = correct_answers == selected_answers
            if is_correct:
                score += question.marks
                
            details[question.id] = {
                'correct': list(correct_answers),
                'selected': list(selected_answers),
                'is_correct': is_correct,
                'marks': question.marks,
                'earned': question.marks if is_correct else 0
            }
        
        # Create result
        result = Result.objects.create(
            session=session,
            score=score,
            total_marks=total_marks,
            details=details
        )
        
        # Update session
        session.end_time = timezone.now()
        session.is_completed = True
        session.save()
        
        return Response(ResultSerializer(result).data)

class AnswerViewSet(viewsets.ModelViewSet):
    serializer_class = AnswerSerializer
    
    def get_queryset(self):
        queryset = Answer.objects.all()
        user = self.request.user
        
        if user.is_authenticated and user.user_type == 'student':
            return queryset.filter(session__student=user)
        return queryset
    
    def perform_create(self, serializer):
        session = serializer.validated_data['session']
        
        # Validate that session belongs to current user
        if session.student != self.request.user:
            raise PermissionDenied("You don't have permission for this session")
            
        # Validate that session is active
        if session.is_completed:
            raise ValidationError("Exam session has already ended")
            
        serializer.save()


class ResultViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ResultSerializer
    
    def get_queryset(self):
        queryset = Result.objects.all()
        user = self.request.user
        
        if user.is_authenticated:
            if user.user_type == 'student':
                return queryset.filter(session__student=user)
            elif user.user_type == 'teacher':
                return queryset.filter(session__exam__subject__teacher=user)
        return queryset
    