from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from rest_framework.filters import SearchFilter

import openpyxl
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
            'full_name': user.first_name + ' ' + user.last_name,
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
    filter_backends = [SearchFilter]
    search_fields = ["text"]

    def get_queryset(self):
        qs = Question.objects.all()
        subject_id = self.request.query_params.get("subject")
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        return qs.order_by("-id")

    # ================= BULK UPLOAD =================
    @action(detail=False, methods=["POST"], url_path="upload-excel")
    def upload_excel(self, request):
        file = request.FILES.get("file")
        subject_id = request.data.get("subject")

        if not file or not subject_id:
            return Response(
                {"error": "file and subject are required"}, status=400
            )

        wb = openpyxl.load_workbook(file)
        sheet = wb.active
        created = 0

        for row in sheet.iter_rows(min_row=2, values_only=True):
            (
                text,
                option_a,
                option_b,
                option_c,
                option_d,
                correct_option,
                marks,
                explanation,
            ) = row

            if not text:
                continue

            Question.objects.update_or_create(
                subject_id=subject_id,
                text=text,
                defaults={
                    "option_a": option_a,
                    "option_b": option_b,
                    "option_c": option_c,
                    "option_d": option_d,
                    "correct_option": correct_option,
                    "marks": marks or 1,
                    "explanation": explanation or "",
                },
            )
            created += 1

        return Response({"status": "success", "created": created})

    # ================= EXCEL TEMPLATE DOWNLOAD =================
    @action(detail=False, methods=["GET"], url_path="download-template")
    def download_template(self, request):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append([
            "text",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "correct_option",
            "marks",
            "explanation",
        ])

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename="mcq_template.xlsx"'
        wb.save(response)
        return response

# ======================================================
# EXAM (MCQ ONLY)
# ======================================================

class ExamViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        qs = (
            Exam.objects
            .select_related("subject")
            .prefetch_related("questions")
            .order_by("-created_at")
        )

        # STUDENT: published + enrolled subjects only
        if user.user_type == "student":
            enrolled_subjects = Subject.objects.filter(
                studentsubjectenrollment__student=user,
                studentsubjectenrollment__is_active=True
            )
            qs = qs.filter(
                is_published=True,
                subject__in=enrolled_subjects
            )

        subject_id = self.request.query_params.get("subject")
        if subject_id:
            qs = qs.filter(subject_id=subject_id)

        return qs


    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        exam = self.get_object()
        exam.is_published = True
        exam.save()
        return Response({"published": True})

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        exam = self.get_object()
        exam.is_published = False
        exam.save()
        return Response({"published": False})
    
# ======================================================
# EXAM SESSION
# ======================================================
    

class ExamSessionViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSessionSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == "student":
            return ExamSession.objects.filter(student=user)
        return ExamSession.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        session = serializer.save()
        return Response(self.get_serializer(session).data, status=201)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        session = self.get_object()

        if session.student != request.user:
            raise PermissionDenied()

        if session.is_completed:
            return Response({"error": "Already submitted"}, status=400)

        answers = request.data.get("answers", [])
        Answer.objects.filter(session=session).delete()

        score = total = 0
        for a in answers:
            q = Question.objects.get(id=a["question"])
            total += q.marks
            if a["selected_answers"] == q.correct_option:
                score += q.marks

            Answer.objects.create(
                session=session,
                question=q,
                selected_answers=a["selected_answers"],
            )

        Result.objects.create(
            session=session,
            score=score,
            total_marks=total,
        )

        session.is_completed = True
        session.end_time = timezone.now()
        session.save()

        return Response({"score": score, "total": total})

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
