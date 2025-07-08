from datetime import time, timedelta
import os
import platform
import tempfile
import threading
from django.shortcuts import get_object_or_404
import docker
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
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
from rest_framework.permissions import IsAuthenticated
from .permissions import IsAdminUserOnly
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.conf import settings
import random


logger = logging.getLogger(__name__)
User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username_or_email = request.data.get('username_or_email')
        password = request.data.get('password')

        if not username_or_email or not password:
            return Response({"error": "Username/email and password required."}, status=status.HTTP_400_BAD_REQUEST)

        user_qs = User.objects.filter(Q(username=username_or_email) | Q(email=username_or_email))
        if not user_qs.exists():
            return Response({"username_or_email": ["User with this email or username does not exist."]}, status=status.HTTP_400_BAD_REQUEST)

        # Try authenticate by username first
        user = authenticate(username=username_or_email, password=password)

        # If not found, try by email username
        if not user:
            try:
                email_user = User.objects.get(email=username_or_email)
                user = authenticate(username=email_user.username, password=password)
            except User.DoesNotExist:
                user = None

        if not user:
            return Response({"password": ["Incorrect password."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token, created = Token.objects.get_or_create(user=user)
        except Exception:
            return Response({"error": "Authentication system error. Please contact support."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": getattr(user, "user_type", None),
            "token": token.key,
            "refresh_token": token.key,  # Placeholder; replace with real refresh token system
            "force_password_change": getattr(user, "force_password_change", False),
            "first_name": user.first_name,
            "is_verified": getattr(user, "is_verified", False)
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
            'Correct Answers': ['B', 'B'],
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
        # Ensure file exists in request.FILES
        if 'file' not in request.FILES:
            return Response(
                {'status': 'error', 'message': 'No file uploaded'},
                status=400
            )

        file = request.FILES['file']

        try:
            # Handle different Excel formats
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file, engine='openpyxl')
            elif file.name.endswith('.xls'):
                df = pd.read_excel(file, engine='xlrd')
            else:
                return Response(
                    {'status': 'error', 'message': 'Invalid file format'},
                    status=400
                )
        except Exception as e:
            return Response(
                {'status': 'error', 'message': f'Failed to read file: {str(e)}'},
                status=400
            )

        required_columns = [
            'Subject', 'Question',
            'Option A', 'Option B', 'Option C', 'Option D',
            'Correct Answers', 'Marks', 'Is Multi'
        ]
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            return Response({'status': 'error', 'message': f'Missing columns: {", ".join(missing_cols)}'}, status=400)

        try:
            with transaction.atomic():
                for idx, row in df.iterrows():
                    raw_subject = row['Subject']
                    if pd.isna(raw_subject) or str(raw_subject).strip() == '':
                        raise ValueError(f"Row {idx+2}: 'Subject' cannot be blank.")

                    subject_obj, _ = Subject.objects.get_or_create(name=str(raw_subject).strip())

                    correct_answers = str(row['Correct Answers']).replace(' ', '').upper()
                    is_multi_val = row['Is Multi']
                    is_multi = str(is_multi_val).strip().lower() in ['true', '1', 'yes']

                    if not is_multi:
                        if ',' in correct_answers:
                            raise ValueError(f"Row {idx+2}: multiple answers '{correct_answers}' given for a single-answer question.")
                        if correct_answers not in ['A', 'B', 'C', 'D']:
                            raise ValueError(f"Row {idx+2}: invalid single correct answer '{correct_answers}'.")
                    else:
                        for opt in correct_answers.split(','):
                            if opt not in ['A', 'B', 'C', 'D']:
                                raise ValueError(f"Row {idx+2}: invalid correct option '{opt}'.")

                    Question.objects.create(
                        subject=subject_obj,
                        text=str(row['Question']).strip(),
                        option_a=str(row['Option A']).strip(),
                        option_b=str(row['Option B']).strip(),
                        option_c=str(row['Option C']).strip(),
                        option_d=str(row['Option D']).strip(),
                        correct_option=correct_answers,
                        marks=int(row['Marks']),
                        is_multi=is_multi
                    )

                return Response({'status': 'success', 'message': 'Questions uploaded successfully'})
        except ValueError as ve:
            return Response({'status': 'error', 'message': str(ve)}, status=400)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=400)

class ExamViewSet(viewsets.ModelViewSet):
    queryset = Exam.objects.all()
    serializer_class = ExamSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'student':
            return Exam.objects.filter(is_published=True)
        return Exam.objects.all()

    @action(detail=True, methods=['POST'])
    def publish(self, request, pk=None):
        exam = self.get_object()
        exam.is_published = True
        exam.save()
        
        message = request.data.get('message', f'New exam "{exam.title}" scheduled')
        students = User.objects.filter(user_type='student', is_active=True)
        
        for student in students:
            if student.email:
                send_mail(
                    subject=f"New Exam: {exam.title}",
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[student.email],
                    fail_silently=True,
                )
        
        return Response({
            'status': 'published', 
            'recipients': students.count()
        })

    @action(detail=True, methods=['POST'])
    def unpublish(self, request, pk=None):
        exam = self.get_object()
        exam.is_published = False
        exam.save()
        return Response({'status': 'unpublished'})

class ExamSessionViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSessionSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'student':
            return ExamSession.objects.filter(student=user)
        elif user.user_type == 'teacher':
            return ExamSession.objects.filter(exam__subject__teacher=user)
        return ExamSession.objects.all()

    def create(self, request, *args, **kwargs):
        student = request.user
        exam_id = request.data.get('exam')
        
        if not exam_id:
            return Response({'error': 'Exam required'}, status=400)

        exam = get_object_or_404(Exam, id=exam_id)

        # Strict mode validation
        if exam.mode == 'strict':
            if ExamSession.objects.filter(
                student=student, 
                exam=exam, 
                is_completed=True
            ).exists():
                return Response(
                    {'error': 'Strict exam already completed. No retries allowed.'},
                    status=400
                )

        # Prevent multiple active sessions
        existing_session = ExamSession.objects.filter(
            student=student, 
            exam=exam, 
            is_completed=False
        ).first()
        
        if existing_session:
            return Response(
                {'error': 'Active session already exists for this exam'},
                status=400
            )

        session = ExamSession(student=student, exam=exam, is_completed=False)

        try:
            session.clean()
            session.save()
        except ValidationError as e:
            return Response({'error': str(e)}, status=400)

        serializer = self.get_serializer(session)
        return Response(serializer.data, status=201)
    
    @action(detail=False, methods=['post'], url_path='validate-exam/(?P<exam_id>[0-9]+)')
    def validate_exam(self, request, exam_id=None):
        student = request.user
        
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response(
                {'error': 'Exam not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            # Strict mode validation
            if exam.mode == 'strict':
                if ExamSession.objects.filter(
                    student=student,
                    exam=exam,
                    is_completed=True
                ).exists():
                    return Response(
                        {'error': 'Strict exam already completed. No retries allowed.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Find existing incomplete session
            session = ExamSession.objects.filter(
                student=student,
                exam=exam,
                is_completed=False
            ).first()

            # Create new session if none exists
            if not session:
                session = ExamSession(student=student, exam=exam, is_completed=False)
                session.clean()
                session.save()

            serializer = ExamSessionSerializer(session)
            return Response(serializer.data)

        except ValidationError as e:
            logger.error(f"[SessionValidationError] {str(e)}")
            return Response(
                {'error': f'Validation error: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.exception(f"[SessionValidationError] Unexpected error: {str(e)}")
            return Response(
                {'error': 'Unable to validate session'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['POST'])
    def start_exam(self, request, pk=None):
        session = self.get_object()
        if session.student != request.user:
            raise PermissionDenied("Invalid session owner")
        
        if not session.start_time:
            session.start_time = timezone.now()
            session.save()
            
        return Response({
            'status': 'exam started',
            'start_time': session.start_time
        })

    @action(detail=True, methods=['POST'], url_path='save_progress')
    def save_progress(self, request, pk=None):
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
            return Response({'error': 'Answers must be a list'}, status=400)

        # Delete existing answers
        Answer.objects.filter(session=session).delete()

        # Create new answers
        for answer_data in answers_data:
            question_id = answer_data.get('question')
            selected_answers = answer_data.get('selected_answers', '')
            
            if question_id:
                Answer.objects.create(
                    session=session,
                    question_id=question_id,
                    selected_answers=selected_answers
                )

        session.elapsed_time = elapsed_time
        session.save()
        
        return Response({'status': 'progress saved'}, status=200)

    @action(detail=True, methods=['POST'])
    def submit_exam(self, request, pk=None):
        session = self.get_object()
        user = request.user

        if session.student != user:
            raise PermissionDenied("Invalid session owner")
            
        if session.is_completed:
            return Response({'error': 'Exam already submitted'}, status=400)

        answers_data = request.data.get('answers', [])
        elapsed_time = request.data.get('elapsed_time', 0)
        termination_reason = request.data.get('termination_reason', None)

        # Save answers
        Answer.objects.filter(session=session).delete()
        for answer_data in answers_data:
            question_id = answer_data.get('question')
            selected_answers = answer_data.get('selected_answers', '')
            
            if question_id:
                Answer.objects.create(
                    session=session,
                    question_id=question_id,
                    selected_answers=selected_answers
                )

        # Calculate results
        answers = Answer.objects.filter(session=session)
        total_marks = 0
        score = 0
        details = {}

        for answer in answers:
            question = answer.question
            total_marks += question.marks
            
            correct_set = set(question.correct_option.split(','))
            selected_set = set(answer.selected_answers.split(',')) if answer.selected_answers else set()
            
            is_correct = correct_set == selected_set
            earned = question.marks if is_correct else 0
            score += earned
            
            details[question.id] = {
                'correct': list(correct_set),
                'selected': list(selected_set),
                'is_correct': is_correct,
                'marks': question.marks,
                'earned': earned
            }

        # Create result
        result = Result.objects.create(
            session=session,
            score=score,
            total_marks=total_marks,
            details=details
        )

        # Complete session
        session.end_time = timezone.now()
        session.is_completed = True
        session.elapsed_time = elapsed_time
        
        if termination_reason:
            session.termination_reason = termination_reason
            
        session.save()

        return Response(ResultSerializer(result).data, status=200)

class AnswerViewSet(viewsets.ModelViewSet):
    serializer_class = AnswerSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get_queryset(self):
        return Answer.objects.filter(session__student=self.request.user)

    def perform_create(self, serializer):
        session = serializer.validated_data['session']
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
        return Result.objects.all()

    @action(detail=False, methods=['GET'], url_path='session/(?P<session_id>[0-9]+)')
    def by_session(self, request, session_id=None):
        session = get_object_or_404(ExamSession, id=session_id)
        user = request.user

        # Authorization check
        if user.user_type == 'student' and session.student != user:
            return Response({'error': 'Permission denied'}, status=403)

        result = get_object_or_404(Result, session=session)
        answers = Answer.objects.filter(session=session).select_related('question')
        
        # Calculate results
        total_right = 0
        total_wrong = 0
        detailed_answers = {}

        for answer in answers:
            q = answer.question
            correct = q.correct_option.split(',') if ',' in q.correct_option else [q.correct_option]
            selected = answer.selected_answers.split(',') if answer.selected_answers else []
            is_correct = sorted(correct) == sorted(selected)

            if is_correct:
                total_right += 1
            else:
                total_wrong += 1

            detailed_answers[q.id] = {
                'question_text': q.text,
                'correct': correct,
                'selected': selected,
                'is_correct': is_correct,
                'marks': q.marks,
                'earned': q.marks if is_correct else 0,
                'explanation': q.explanation or ''
            }

        # Prepare response
        pass_status = "Pass" if result.score >= (0.8 * result.total_marks) else "Fail"
        
        return Response({
            'exam_title': session.exam.title,
            'submitted_at': session.end_time,
            'duration': session.exam.duration,
            'student_name': session.student.get_full_name() or session.student.username,
            'score': result.score,
            'total_marks': result.total_marks,
            'right_answers': total_right,
            'wrong_answers': total_wrong,
            'result': pass_status,
            'termination_reason': session.termination_reason,
            'details': detailed_answers,
        })

def generate_otp():
    return str(random.randint(100000, 999999))

class SendOTPView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        otp = generate_otp()

        EmailOTP.objects.update_or_create(
            user=user, 
            defaults={'otp': otp, 'created_at': timezone.now()}
        )
        
        send_mail(
            'Your Exam Platform OTP Code',
            f'Your OTP is {otp}',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return Response({'message': 'OTP sent successfully'})

class VerifyOTPView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        otp = request.data.get('otp')
        user = request.user

        try:
            email_otp = EmailOTP.objects.get(user=user)
            # Check expiration (5 minutes)
            if timezone.now() > email_otp.created_at + timedelta(minutes=5):
                return Response({'error': 'OTP expired'}, status=400)
                
            if email_otp.otp == otp:
                user.is_verified = True
                user.save()
                email_otp.delete()
                return Response({'message': 'Email verified successfully'})
            return Response({'error': 'Invalid OTP'}, status=400)
        except EmailOTP.DoesNotExist:
            return Response({'error': 'OTP not sent'}, status=400)


class GetStudentEmailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            student = User.objects.get(id=user_id, user_type='student')
            return Response({'email': student.email})
        except User.DoesNotExist:
            return Response({'error': 'Student not found'}, status=404)



class PracticalExamViewSet(viewsets.ModelViewSet):
    queryset = PracticalExam.objects.all()
    serializer_class = PracticalExamSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'student':
            return PracticalExam.objects.filter(is_published=True)
        return PracticalExam.objects.all()


class PracticalExamSessionViewSet(viewsets.ModelViewSet):
    serializer_class = PracticalExamSessionSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'delete', 'head', 'options', 'trace']

    def get_queryset(self):
        return PracticalExamSession.objects.filter(student=self.request.user)

    @action(detail=True, methods=['get'])
    def token(self, request, pk=None):
        session = self.get_object()
        return Response({'token': session.token})
    
    @action(detail=True, methods=['get'])
    def container_status(self, request, pk=None):
        session = self.get_object()
        return Response({
            'status': session.get_container_status(),
            'container_id': session.container_id
        })
    
    @action(detail=True, methods=['post'])
    def restart_container(self, request, pk=None):
        session = self.get_object()
        try:
            # Force remove existing container if any
            if session.container_id:
                try:
                    client = docker.from_env()
                    try:
                        container = client.containers.get(session.container_id)
                        container.stop(timeout=1)
                        container.remove(force=True)
                    except docker.errors.NotFound:
                        pass
                except Exception as e:
                    logger.error(f"Container removal error: {str(e)}")
            
            # Reset session container info
            session.container_id = None
            session.verification_output = None
            session.is_success = False
            session.termination_reason = None
            session.status = 'running'
            session.save()
            
            # Start new container in background thread
            threading.Thread(target=session.start_container).start()
            
            return Response({
                'status': 'restarting',
                'message': 'Container is being restarted'
            })
        except Exception as e:
            logger.exception("Container restart failed")
            return Response({
                'error': 'Container restart failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs):
        user = request.user
        exam_id = request.data.get('exam')
        
        if not exam_id:
            return Response({'error': 'Exam ID required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Check for existing session
            existing_session = PracticalExamSession.objects.filter(
                student=user, 
                exam_id=exam_id,
                status='running'
            ).first()
            
            if existing_session:
                return Response(
                    PracticalExamSessionSerializer(existing_session).data,
                    status=status.HTTP_200_OK
                )
            
            # Create new session
            session = PracticalExamSession.objects.create(
                student=user,
                exam_id=exam_id,
                status='starting'  # New initial status
            )
            
            # Start container in background thread
            threading.Thread(target=session.start_container).start()
            
            return Response(
                PracticalExamSessionSerializer(session).data, 
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            logger.exception("Session creation failed")
            return Response({
                'error': 'Session creation failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        session = self.get_object()
        user = request.user
        
        if session.student != user:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        if session.status != 'running':
            return Response({
                'error': 'Session not active',
                'current_status': session.status
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            output = session.execute_command(session.exam.verification_command)
            success = "success" in output.lower() or "ok" in output.lower()
            
            session.status = 'completed'
            session.end_time = timezone.now()
            session.verification_output = output[:10000]
            session.is_success = success
            session.save()
            
            session.terminate_container()
            
            return Response({
                'is_success': success,
                'verification_output': output[:5000]
            })
        except Exception as e:
            logger.exception("Verification failed")
            return Response({
                'error': 'Verification failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        session = self.get_object()
        user = request.user
        
        if session.student != user:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        if session.status != 'running':
            return Response({
                'error': 'Session not active',
                'current_status': session.status
            }, status=status.HTTP_400_BAD_REQUEST)
        
        reason = request.data.get('reason', 'Terminated by student')[:200]
        
        try:
            session.terminate_container()
            session.status = 'terminated'
            session.end_time = timezone.now()
            session.termination_reason = reason
            session.save()
            
            return Response({
                'status': 'terminated',
                'session_id': session.id,
                'termination_reason': reason
            })
        except Exception as e:
            logger.exception("Termination failed")
            return Response({
                'error': 'Termination failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def destroy(self, request, *args, **kwargs):
        session = self.get_object()
        if session.status == 'running':
            session.terminate_container()
        return super().destroy(request, *args, **kwargs)
    


class PracticalExamResultViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PracticalExamResultSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'student':
            return PracticalExamResult.objects.filter(session__student=user)
        return PracticalExamResult.objects.all()