from datetime import timedelta
from time import time
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import *
from .serializers import *
from django.utils import timezone
from django.http import HttpResponse
import pandas as pd
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
from django.db.models import Prefetch
from .serializers import StudentExamSerializer
from django.core.mail import send_mail
import threading
from .verification import verification_system




logger = logging.getLogger(__name__)
User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsAdminUserOnly]
    authentication_classes = [TokenAuthentication]


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            token, created = Token.objects.get_or_create(user=user)
            
            return Response({
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.user_type,
                "token": token.key,
                "refresh_token": token.key,  # In a real app, use proper refresh tokens
                "force_password_change": user.force_password_change,
                "first_name": user.first_name,
                "is_verified": user.is_verified,
                "subjects": SubjectSerializer(user.subjects.all(), many=True).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
    permission_classes = [IsAuthenticated, IsAdminUserOnly]
    authentication_classes = [TokenAuthentication]


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
            # Only show exams for the student's subjects
            return Exam.objects.filter(
                subject__in=user.subjects.all(),
                is_published=True
            )
        return Exam.objects.all()

    @action(detail=True, methods=['POST'])
    def publish(self, request, pk=None):
        exam = self.get_object()
        exam.is_published = True
        exam.save()
        
        message = request.data.get('message', f'New exam "{exam.title}" scheduled')
        students = User.objects.filter(
            user_type='student', 
            is_active=True,
            subjects=exam.subject  # Only notify students with this subject
        )
        
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
    

class StudentExamViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StudentExamSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'student':
            # Only show exams for the student's subjects
            return Exam.objects.filter(
                subject__in=user.subjects.all(),
                is_published=True
            )
        return Exam.objects.none()
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
        

class ExamSessionViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSessionSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get_queryset(self):
        user = self.request.user
        queryset = ExamSession.objects.select_related(
            'exam', 'exam__subject'
        ).prefetch_related(
            Prefetch('answers', queryset=Answer.objects.select_related('question')),
            Prefetch('exam__examquestion_set', 
                     queryset=ExamQuestion.objects.select_related('question'))
        )
        
        if user.user_type == 'student':
            return queryset.filter(student=user)
        return queryset

    def create(self, request, *args, **kwargs):
        student = request.user
        exam_id = request.data.get('exam')
        
        if not exam_id:
            return Response({'error': 'Exam required'}, status=400)

        exam = get_object_or_404(Exam, id=exam_id)
        
        # Check if student has this subject
        if student.user_type == 'student' and exam.subject not in student.subjects.all():
            return Response(
                {'error': 'You are not enrolled in this subject'},
                status=status.HTTP_403_FORBIDDEN
            )

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
        
        # Check if student has this subject
        if student.user_type == 'student' and exam.subject not in student.subjects.all():
            return Response(
                {'error': 'You are not enrolled in this subject'},
                status=status.HTTP_403_FORBIDDEN
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
            # Only show practical exams for the student's subjects
            return PracticalExam.objects.filter(
                subject__in=user.subjects.all(),
                is_published=True
            )
        return PracticalExam.objects.all()


class PracticalExamSessionViewSet(viewsets.ModelViewSet):
    queryset = PracticalExamSession.objects.all()
    serializer_class = PracticalExamSessionSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, "user_type", None) == 'student':
            return PracticalExamSession.objects.filter(student=user)
        return PracticalExamSession.objects.all()

    def create(self, request, *args, **kwargs):
        student = request.user
        exam_id = request.data.get('exam')
        if not exam_id:
            return Response({'error': 'Exam required'}, status=400)

        exam = get_object_or_404(PracticalExam, id=exam_id)
        if getattr(student, "user_type", None) == 'student' and hasattr(student, "subjects") and exam.subject not in student.subjects.all():
            return Response({'error': 'Not enrolled in subject'}, status=status.HTTP_403_FORBIDDEN)

        # Check if student already has an active session for this exam
        existing = PracticalExamSession.objects.filter(
            student=student, 
            exam=exam,
            status__in=['starting', 'running']
        ).first()
        
        if existing:
            return Response({
                'error': 'You already have an active session for this exam',
                'session_id': existing.id
            }, status=400)

        # Create new session
        session = PracticalExamSession(student=student, exam=exam)
        session.status = 'starting'
        session.save()

        # Start VM creation in background thread with resource limits
        t = threading.Thread(target=self.start_vm_with_limits, args=(session,), daemon=True)
        t.start()

        serializer = self.get_serializer(session)
        return Response(serializer.data, status=201)
    
    def start_vm_with_limits(self, session):
        """Start VM with resource limits to prevent system overload"""
        try:
            # Check current VM count to avoid overloading the system
            active_vms = PracticalExamSession.objects.filter(
                status__in=['starting', 'running']
            ).count()
            
            # If too many VMs are running, wait before starting a new one
            if active_vms > 10:  # Adjust based on your system capacity
                time.sleep(30)
            
            # Start the VM
            session.start_vm()
        except Exception as e:
            logger.error(f"Failed to start VM for session {session.id}: {str(e)}")
            session.status = 'failed'
            session.startup_log = f"VM startup failed: {str(e)}"
            session.save()

    @action(detail=True, methods=['POST'])
    def terminate(self, request, pk=None):
        session = self.get_object()
        if session.student != request.user:
            return Response({'error': 'Invalid session owner'}, status=status.HTTP_403_FORBIDDEN)
        
        reason = request.data.get('reason', 'Manual termination')
        session.termination_reason = reason
        session.terminate_vm()
        session.status = 'terminated'
        session.end_time = timezone.now()
        session.save()
        
        return Response({'status': 'session terminated'})

    @action(detail=True, methods=['POST'])
    def verify(self, request, pk=None):
        session = get_object_or_404(PracticalExamSession, pk=pk)
        if session.student != request.user:
            return Response({'error': 'Invalid session owner'}, status=status.HTTP_403_FORBIDDEN)
        if session.status != 'running':
            return Response({'error': 'Session not running'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Terminate the VM first
        session.terminate_vm()
        session.status = 'verifying'
        session.save()
        
        # Run verification using the improved verification system
        result = verification_system.run_verification(session.id)
        
        return Response({
            'status': result.get('status', 'started'), 
            'message': 'Verification process has started. Results will be available shortly.'
        })

    @action(detail=True, methods=['GET'])
    def verification_status(self, request, pk=None):
        """Check the status of a verification process"""
        session = get_object_or_404(PracticalExamSession, pk=pk)
        if session.student != request.user:
            return Response({'error': 'Invalid session owner'}, status=status.HTTP_403_FORBIDDEN)
        
        # Check if verification is complete
        if session.status in ['completed', 'failed']:
            return Response({
                'status': session.status,
                'completed': True,
                'is_success': session.is_success,
                'score': getattr(session, 'score', None),
                'details': getattr(session, 'verification_output', {})
            })
        
        # Check if verification is still in progress
        status_info = verification_system.get_verification_status(session.id)
        if status_info:
            return Response(status_info)
        
        return Response({
            'status': 'unknown',
            'message': 'Verification status could not be determined'
        }, status=404)

    @action(detail=True, methods=['GET'])
    def vm_status(self, request, pk=None):
        session = self.get_object()
        status_str = session.get_vm_status()
        return Response({'status': status_str, 'vm_name': session.vm_name})

    @action(detail=True, methods=['POST'])
    def restart_vm(self, request, pk=None):
        session = self.get_object()
        if session.student != request.user:
            raise PermissionDenied("Invalid session owner")
        session.terminate_vm()
        session.status = 'starting'
        session.startup_log = ''
        session.verification_output = ''
        session.is_success = False
        session.termination_reason = ''
        session.save()
        
        # Start VM in background thread with limits
        t = threading.Thread(target=self.start_vm_with_limits, args=(session,), daemon=True)
        t.start()
        
        return Response({'status': 'VM restart initiated'})
    
    @action(detail=False, methods=['POST'])
    def cleanup_stuck_sessions(self, request):
        """Admin endpoint to cleanup stuck sessions"""
        if not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=403)
        
        # Clean up stuck verification processes
        verification_system.cleanup_stuck_processes()
        
        # Clean up stuck VM sessions
        stuck_sessions = PracticalExamSession.objects.filter(
            status__in=['starting', 'running'],
            start_time__lt=timezone.now() - timezone.timedelta(minutes=30)
        )
        
        for session in stuck_sessions:
            session.terminate_vm()
            session.status = 'failed'
            session.termination_reason = 'Session was stuck and automatically terminated'
            session.save()
        
        return Response({
            'status': 'cleanup_completed',
            'sessions_terminated': stuck_sessions.count()
        })
    
       
    
class PracticalExamResultViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PracticalExamResultSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'student':
            return PracticalExamResult.objects.filter(session__student=user)
        return PracticalExamResult.objects.all()