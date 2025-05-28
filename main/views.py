from rest_framework import viewsets, status, filters
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
        }, status=status.HTTP_200_OK)
    

class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer

class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.all()
    serializer_class = ExamQuestionSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['subject']
    search_fields = ['text']
    
    @action(detail=False, methods=['POST'])
    def bulk_upload(self, request):
        file = request.FILES['file']
        process_excel(file)
        return Response({'status': 'success'})
    
    @action(detail=False, methods=['GET'])
    def download_format(self, request):
        data = {
            'Subject': ['Math'],
            'Question': ['What is 2+2?'],
            'Option A': ['3'],
            'Option B': ['4'],
            'Option C': ['5'],
            'Option D': ['6'],
            'Correct Answer': ['B'],
            'Marks': [1]
        }
        df = pd.DataFrame(data)
        response = HttpResponse(content_type='application/ms-excel')
        response['Content-Disposition'] = 'attachment; filename="question_format.xlsx"'
        df.to_excel(response, index=False)
        return response

class ExamViewSet(viewsets.ModelViewSet):
    queryset = Exam.objects.all()
    serializer_class = ExamSerializer
    
    @action(detail=True, methods=['POST'])
    def publish(self, request, pk=None):
        exam = self.get_object()
        exam.is_published = True
        exam.save()
        return Response({'status': 'published'})
    
    @action(detail=True, methods=['POST'])
    def unpublish(self, request, pk=None):
        exam = self.get_object()
        exam.is_published = False
        exam.save()
        return Response({'status': 'unpublished'})

class ExamSessionViewSet(viewsets.ModelViewSet):
    queryset = ExamSession.objects.all()
    serializer_class = ExamSessionSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        if user.is_authenticated and user.user_type == 'student':
            return queryset.filter(student=user)
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
        # Calculate score and create result
        return Response({'status': 'exam submitted'})

class AnswerViewSet(viewsets.ModelViewSet):
    queryset = Answer.objects.all()
    serializer_class = AnswerSerializer

class ResultViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Result.objects.all()
    serializer_class = ResultSerializer

    