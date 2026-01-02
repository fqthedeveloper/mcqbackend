from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction

from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import PermissionDenied

import random

from .models import (
    User, Subject, StudentSubjectEnrollment,
    Question, Exam, ExamSession, Answer, Result, EmailOTP
)
from .serializers import *
from .permissions import IsAdminUserOnly, IsStudentUserOnly

UserModel = get_user_model()

# ======================================================
# USER
# ======================================================

class UserViewSet(viewsets.ModelViewSet):
    queryset = UserModel.objects.all()
    serializer_class = UserSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUserOnly]


class StudentViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(user_type='student')
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    def get_serializer_class(self):
        if self.action == 'create':
            return StudentCreateSerializer
        if self.action in ['update', 'partial_update']:
            return StudentUpdateSerializer
        return UserSerializer

    @action(detail=True, methods=['GET'])
    def enrolled_subjects(self, request, pk=None):
        enrollments = StudentSubjectEnrollment.objects.filter(
            student_id=pk, is_active=True
        )
        subjects = [e.subject for e in enrollments]
        return Response(SubjectSerializer(subjects, many=True).data)


class StudentSubjectEnrollmentViewSet(viewsets.ModelViewSet):
    queryset = StudentSubjectEnrollment.objects.all()
    serializer_class = StudentSubjectEnrollmentSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUserOnly]

    @action(detail=False, methods=['POST'])
    def bulk_enroll(self, request):
        subject_id = request.data.get('subject_id')
        student_ids = request.data.get('student_ids', [])

        created = []
        for sid in student_ids:
            obj, _ = StudentSubjectEnrollment.objects.update_or_create(
                student_id=sid,
                subject_id=subject_id,
                defaults={'is_active': True}
            )
            created.append(obj.id)

        return Response({
            'status': 'bulk_enroll_success',
            'count': len(created)
        })

    @action(detail=False, methods=['POST'])
    def bulk_assign_subjects(self, request):
        student_id = request.data.get('student_id')
        subject_ids = request.data.get('subject_ids', [])

        created = []
        for sub_id in subject_ids:
            obj, _ = StudentSubjectEnrollment.objects.update_or_create(
                student_id=student_id,
                subject_id=sub_id,
                defaults={'is_active': True}
            )
            created.append(obj.id)

        return Response({
            'status': 'bulk_assign_success',
            'count': len(created)
        })
        
# ======================================================
# AUTH
# ======================================================

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        user = authenticate(
            username=request.data.get('username_or_email'),
            password=request.data.get('password')
        )

        if not user:
            return Response({'error': 'Invalid credentials'}, status=400)

        token, _ = Token.objects.get_or_create(user=user)

        return Response({
            'token': token.key,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': user.user_type,
            'email': user.email,
            'force_password_change': user.force_password_change,
            'is_verified': user.is_verified
        })


class ForcePasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        request.user.set_password(serializer.validated_data['new_password'])
        request.user.force_password_change = False
        request.user.save()

        return Response({'message': 'Password changed'})


# ======================================================
# OTP
# ======================================================

def generate_otp():
    return str(random.randint(100000, 999999))


class SendOTPView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def post(self, request):
        otp = generate_otp()

        EmailOTP.objects.update_or_create(
            user=request.user,
            defaults={'otp': otp}
        )

        send_mail(
            'Your OTP',
            f'Your OTP is {otp}',
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email]
        )

        return Response({'message': 'OTP sent'})


class VerifyOTPView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def post(self, request):
        record = get_object_or_404(EmailOTP, user=request.user)

        if record.otp != request.data.get('otp'):
            return Response({'error': 'Invalid OTP'}, status=400)

        request.user.is_verified = True
        request.user.save()
        record.delete()

        return Response({'message': 'Verified'})


# ======================================================
# SUBJECT
# ======================================================

class SubjectViewSet(viewsets.ModelViewSet):
    serializer_class = SubjectSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.user_type == 'student':
            return Subject.objects.filter(
                studentsubjectenrollment__student=self.request.user,
                studentsubjectenrollment__is_active=True
            )
        return Subject.objects.all()


# ======================================================
# QUESTION
# ======================================================

class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.user_type == 'student':
            return Question.objects.filter(
                subject__studentsubjectenrollment__student=self.request.user,
                subject__studentsubjectenrollment__is_active=True
            )
        return Question.objects.all()


# ======================================================
# EXAM (MCQ ONLY)
# ======================================================

class ExamViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.user_type == 'student':
            return Exam.objects.filter(
                subject__studentsubjectenrollment__student=self.request.user,
                subject__studentsubjectenrollment__is_active=True,
                is_published=True
            )
        return Exam.objects.all()

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


# ======================================================
# EXAM SESSION
# ======================================================

class ExamSessionViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSessionSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.user_type == 'student':
            return ExamSession.objects.filter(student=self.request.user)
        return ExamSession.objects.all()

    @action(detail=True, methods=['POST'])
    def start_exam(self, request, pk=None):
        session = self.get_object()
        session.start_time = timezone.now()
        session.save()
        return Response({'status': 'started'})

    @action(detail=True, methods=['POST'])
    def submit_exam(self, request, pk=None):
        session = self.get_object()

        if session.student != request.user:
            raise PermissionDenied()

        answers = request.data.get('answers', [])
        Answer.objects.filter(session=session).delete()

        score = 0
        total = 0

        for a in answers:
            q = Question.objects.get(id=a['question'])
            total += q.marks
            if a['selected_answers'] == q.correct_option:
                score += q.marks
            Answer.objects.create(
                session=session,
                question=q,
                selected_answers=a['selected_answers']
            )

        Result.objects.create(
            session=session,
            score=score,
            total_marks=total
        )

        session.is_completed = True
        session.end_time = timezone.now()
        session.save()

        return Response({'score': score, 'total': total})

    @action(detail=False, methods=['GET'], url_path='validate/(?P<exam_id>[^/.]+)')
    def validate_session(self, request, exam_id=None):
        exists = ExamSession.objects.filter(
            student=request.user,
            exam_id=exam_id,
            is_completed=False
        ).exists()
        return Response({'valid': exists})


# ======================================================
# ANSWER
# ======================================================

class AnswerViewSet(viewsets.ModelViewSet):
    queryset = Answer.objects.all()
    serializer_class = AnswerSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]


# ======================================================
# RESULT
# ======================================================

class ResultViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ResultSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.user_type == 'student':
            return Result.objects.filter(session__student=self.request.user)
        return Result.objects.all()


# ======================================================
# DASHBOARDS
# ======================================================

class StudentDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsStudentUserOnly]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        return Response({
            'subjects': SubjectSerializer(
                Subject.objects.filter(
                    studentsubjectenrollment__student=request.user,
                    studentsubjectenrollment__is_active=True
                ),
                many=True
            ).data,
            'exams': ExamSerializer(
                Exam.objects.filter(
                    subject__studentsubjectenrollment__student=request.user,
                    subject__studentsubjectenrollment__is_active=True,
                    is_published=True
                ),
                many=True
            ).data,
            'active_sessions': ExamSessionSerializer(
                ExamSession.objects.filter(student=request.user, is_completed=False),
                many=True
            ).data
        })


class AdminDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserOnly]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        return Response({
            'total_students': UserModel.objects.filter(user_type='student').count(),
            'total_subjects': Subject.objects.count(),
            'total_questions': Question.objects.count(),
            'total_exams': Exam.objects.count(),
            'active_exams': Exam.objects.filter(is_published=True).count(),
            'total_results': Result.objects.count(),
        })


class MyProfileView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
