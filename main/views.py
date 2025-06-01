from django.shortcuts import get_object_or_404
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
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
import json
from django.conf import settings



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
    permission_classes = [IsAuthenticated, IsAdminUserOnly]
    authentication_classes = [TokenAuthentication]

    def list(self, request, *args, **kwargs):
        print("Logged in user:", request.user)
        print("Returning students:", self.get_queryset())
        return super().list(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):  # <--- This method goes here in the ViewSet
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        old_email = instance.email

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        new_email = serializer.validated_data.get('email', old_email)

        if new_email != old_email:
            send_mail(
                subject='Your email has been updated',
                message=(
                    f'Hello {instance.first_name},\n\n'
                    f'Your email address has been changed to {new_email}.\n'
                    'If you did not request this change, please contact support immediately.'
                ),
                from_email='no-reply@example.com',
                recipient_list=[new_email],
                fail_silently=False,
            )

        return Response(serializer.data, status=status.HTTP_200_OK)


class ForcePasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

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
    serializer_class = QuestionSerializer

    @action(detail=False, methods=['GET'])
    def download_format(self, request):
        data = {
            'Subject': ['Mathematics', 'Science'],
            'Question': ['What is 2+2?', 'Water boils at?'],
            'Option A': ['3', '90°C'],
            'Option B': ['4', '100°C'],
            'Option C': ['5', '110°C'],
            'Option D': ['6', '120°C'],
            'Correct Answers': ['B', 'B'],  # Comma separated for multi
            'Marks': [1, 1],
            'Is Multi': [False, False]
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
            'Subject', 'Question',
            'Option A', 'Option B', 'Option C', 'Option D',
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
                'message': f'Missing columns: {", ".join(missing_cols)}'
            }, status=400)

        try:
            with transaction.atomic():
                for _, row in df.iterrows():
                    subject_obj, _ = Subject.objects.get_or_create(name=row['Subject'])

                    correct_answers = str(row['Correct Answers']).replace(' ', '').upper()

                    is_multi_val = row['Is Multi']
                    is_multi = str(is_multi_val).strip().lower() in ['true', '1', 'yes']

                    if is_multi:
                        if not all(opt in ['A', 'B', 'C', 'D'] for opt in correct_answers.split(',')):
                            raise ValueError(f"Invalid correct options in row: {correct_answers}")
                    else:
                        if correct_answers not in ['A', 'B', 'C', 'D']:
                            raise ValueError(f"Invalid single correct option in row: {correct_answers}")

                    Question.objects.create(
                        subject=subject_obj,
                        text=row['Question'],
                        option_a=row['Option A'],
                        option_b=row['Option B'],
                        option_c=row['Option C'],
                        option_d=row['Option D'],
                        correct_option=correct_answers,
                        marks=int(row['Marks']),
                        is_multi=is_multi
                    )
            return Response({'status': 'success', 'message': 'Questions uploaded successfully'})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=400)


class ExamViewSet(viewsets.ModelViewSet):
    queryset = Exam.objects.all()
    serializer_class = ExamSerializer
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.is_authenticated and hasattr(user, 'user_type') and user.user_type == 'student':
            return qs.filter(is_published=True)
        return qs

    @action(detail=True, methods=['POST'])
    def publish(self, request, pk=None):
        exam = self.get_object()
        exam.is_published = True
        exam.save()

        students = User.objects.filter(user_type='student', is_active=True)
        message = request.data.get(
            'message',
            f'A new exam "{exam.title}" has been scheduled. Please check your dashboard for details.'
        )
        for student in students:
            send_mail(
                subject=f"New Exam: {exam.title}",
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[student.email],
                fail_silently=True
            )
        return Response({'status': 'published', 'recipients': students.count()})

    @action(detail=True, methods=['POST'])
    def unpublish(self, request, pk=None):
        exam = self.get_object()
        exam.is_published = False
        exam.save()
        return Response({'status': 'unpublished'})
    

   # views.py
class ExamSessionViewSet(viewsets.ModelViewSet):
    """
    Handles:
      - create()            → POST /api/sessions/            (creates new session)
      - validate_session()  → GET  /api/sessions/validate/<exam_id>/
      - start_exam()        → POST /api/sessions/<pk>/start_exam/
      - save_progress()     → POST /api/sessions/<pk>/save_progress/
      - submit_exam()       → POST /api/sessions/<pk>/submit_exam/
    """
    serializer_class = ExamSessionSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get_queryset(self):
        user = self.request.user
        qs = ExamSession.objects.all()
        if user.user_type == 'student':
            return qs.filter(student=user)
        elif user.user_type == 'teacher':
            return qs.filter(exam__subject__teacher=user)
        return qs

    def create(self, request, *args, **kwargs):
        student = request.user
        exam_id = request.data.get('exam')
        if not exam_id:
            return Response(
                {'error': 'Exam field is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        exam = get_object_or_404(Exam, id=exam_id)

        existing_session = ExamSession.objects.filter(
            student=student,
            exam=exam,
            is_completed=False
        ).first()

        if existing_session:
            return Response(
                {'error': 'You already have an active session.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        session = ExamSession.objects.create(
            student=student,
            exam=exam,
            is_completed=False
        )
        serializer = self.get_serializer(session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['GET'], url_path='validate/(?P<exam_id>[0-9]+)')
    def validate_session(self, request, exam_id=None):
        """
        If an active, incomplete session exists, return it.
        Otherwise, create a new one.
        """
        student = request.user
        exam = get_object_or_404(Exam, id=exam_id)

        session = ExamSession.objects.filter(
            student=student,
            exam=exam,
            is_completed=False
        ).first()

        if not session:
            try:
                session = ExamSession.objects.create(
                    student=student,
                    exam=exam,
                    is_completed=False
                )
            except IntegrityError:
                # Another thread/request created it first—fetch the existing one
                session = ExamSession.objects.get(student=student, exam=exam)

        serializer = self.get_serializer(session)
        return Response(serializer.data)

    @action(detail=True, methods=['POST'])
    def start_exam(self, request, pk=None):
        """
        Marks the session’s start_time if not already set.
        """
        session = self.get_object()
        if session.student != request.user:
            raise PermissionDenied("You do not own this session.")

        if not session.start_time:
            session.start_time = timezone.now()
            session.save()
        return Response({'status': 'exam started'})

    @action(detail=True, methods=['POST'], url_path='save_progress')
    def save_progress(self, request, pk=None):
        """
        Saves intermediate answers + elapsed_time. 
        Expects payload: { "elapsed_time": <seconds>, "answers": [ { question: <id>, selected_answers: "A,C" }, … ] }
        """
        session = self.get_object()
        user = request.user

        if session.student != user:
            raise PermissionDenied("Invalid session owner")

        # We do not allow saving if already completed
        if session.is_completed:
            return Response(
                {'error': 'Cannot save—exam already submitted.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        answers_data = request.data.get('answers', [])
        elapsed_time = request.data.get('elapsed_time', 0)

        if not isinstance(answers_data, list):
            raise ValidationError("`answers` must be a list of answer objects.")

        # Overwrite any existing saved answers for this session
        Answer.objects.filter(session=session).delete()

        for answer_data in answers_data:
            question_id = answer_data.get('question')
            selected_answers = answer_data.get('selected_answers', '')
            Answer.objects.create(
                session=session,
                question_id=question_id,
                selected_answers=selected_answers
            )

        # Save elapsed_time to the session
        session.elapsed_time = elapsed_time
        session.save()

        return Response({'status': 'progress saved'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'])
    def submit_exam(self, request, pk=None):
        """
        Final submission. Calculates score, marks session complete.
        """
        session = self.get_object()
        user = request.user

        if session.student != user:
            raise PermissionDenied("Invalid session owner")

        if session.is_completed:
            return Response(
                {'error': 'Exam already submitted'},
                status=status.HTTP_400_BAD_REQUEST
            )

        answers_data = request.data.get('answers', [])
        elapsed_time = request.data.get('elapsed_time', 0)

        if not isinstance(answers_data, list):
            raise ValidationError("`answers` must be a list of answer objects.")

        # Overwrite any existing answers
        Answer.objects.filter(session=session).delete()

        for answer_data in answers_data:
            question_id = answer_data.get('question')
            selected_answers = answer_data.get('selected_answers', '')
            Answer.objects.create(
                session=session,
                question_id=question_id,
                selected_answers=selected_answers
            )

        # Grading
        answers = Answer.objects.filter(session=session)
        total_marks = 0
        score = 0
        details = {}

        for answer in answers:
            question = answer.question
            total_marks += question.marks
            correct_set = set(question.correct_option.split(','))
            selected_set = set(answer.selected_answers.split(','))
            is_correct = (correct_set == selected_set)
            earned = question.marks if is_correct else 0
            if is_correct:
                score += earned

            details[question.id] = {
                'correct': list(correct_set),
                'selected': list(selected_set),
                'is_correct': is_correct,
                'marks': question.marks,
                'earned': earned
            }

        result = Result.objects.create(
            session=session,
            score=score,
            total_marks=total_marks,
            details=details
        )

        session.end_time = timezone.now()
        session.is_completed = True
        session.save()

        return Response(ResultSerializer(result).data, status=status.HTTP_200_OK)


class AnswerViewSet(viewsets.ModelViewSet):
    serializer_class = AnswerSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get_queryset(self):
        return Answer.objects.filter(session__student=self.request.user)

    def perform_create(self, serializer):
        session = serializer.validated_data.get('session')
        if session.student != self.request.user:
            raise PermissionDenied("Invalid session owner")
        if session.is_completed:
            raise ValidationError("Session already completed")
        serializer.save()

class ResultViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ResultSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'student':
            return Result.objects.filter(session__student=user)
        return Result.objects.all()  # Teachers can see all results