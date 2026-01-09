from django.db import IntegrityError
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.crypto import get_random_string
from django.core.mail import send_mail

from mcqbackend import settings

from .models import (
    User, Subject, StudentSubjectEnrollment,
    Question, Exam, ExamSession, Answer, Result
)
from .models import *

User = get_user_model()

# ================= USER ================= #

class UserSerializer(serializers.ModelSerializer):
    subjects = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'username',
            'user_type',
            'first_name',
            'last_name',
            'is_verified',
            'is_active',
            'subjects'
        ]

    def get_subjects(self, obj):
        enrollments = StudentSubjectEnrollment.objects.filter(
            student=obj,
            is_active=True
        )
        return SubjectSerializer(
            [e.subject for e in enrollments],
            many=True
        ).data


class StudentCreateSerializer(serializers.ModelSerializer):
    subject_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'subject_ids'
        ]

    def create(self, validated_data):
        subject_ids = validated_data.pop('subject_ids', [])
        password = get_random_string(10)

        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data.get('username', validated_data['email']),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            user_type='student',
            password=password,
            force_password_change=True,
            is_active=True
        )

        for subject_id in subject_ids:
            StudentSubjectEnrollment.objects.update_or_create(
                student=user,
                subject_id=subject_id,
                defaults={'is_active': True}
            )

        send_mail(
            subject="IRT Student Account Created - MCQ Exam System",
            message=f"""
                Hello {user.first_name or user.username},

                Email: {user.email}
                Password: {password}

                """,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[user.email],
                            fail_silently=False,
                        )

        return user


class StudentUpdateSerializer(serializers.ModelSerializer):
    subject_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'is_active',
            'subject_ids'
        ]

    def update(self, instance, validated_data):
        subject_ids = validated_data.pop('subject_ids', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if subject_ids is not None:
            # ❗ FULL REPLACE (update, not enroll)
            StudentSubjectEnrollment.objects.filter(
                student=instance
            ).update(is_active=False)

            for sid in subject_ids:
                StudentSubjectEnrollment.objects.update_or_create(
                    student=instance,
                    subject_id=sid,
                    defaults={'is_active': True}
                )

        return instance
    
    
class PasswordChangeSerializer(serializers.Serializer):
    new_password = serializers.CharField(validators=[validate_password])
    confirm_password = serializers.CharField()

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match")
        return data


# ================= SUBJECT ================= #

class SubjectSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = [
            'id',
            'name',
            'description',
            'is_active',
            'question_count'
        ]

    def get_question_count(self, obj):
        return Question.objects.filter(subject=obj).count()


# ================= ENROLLMENT ================= #

class StudentSubjectEnrollmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentSubjectEnrollment
        fields = ['id', 'student', 'subject', 'is_active']


# ================= QUESTION ================= #

class QuestionSerializer(serializers.ModelSerializer):
    correct_answers = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=True
    )
    
    subject_name = serializers.CharField(source="subject.name", read_only=True)


    class Meta:
        model = Question
        fields = [
            "id",
            "subject",
            "subject_name",
            "text",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "correct_option",
            "correct_answers",
            "marks",
            "explanation",
        ]
        read_only_fields = ["correct_option"]

    def validate_correct_answers(self, value):
        # Normalize + validate
        allowed = {"A", "B", "C", "D"}
        cleaned = [v.upper() for v in value]

        invalid = set(cleaned) - allowed
        if invalid:
            raise serializers.ValidationError(
                f"Invalid answer(s): {', '.join(invalid)}"
            )

        return cleaned

    def create(self, validated_data):
        answers = validated_data.pop("correct_answers")
        validated_data["correct_option"] = ",".join(answers)
        return Question.objects.create(**validated_data)

    def update(self, instance, validated_data):
        answers = validated_data.pop("correct_answers", None)

        if answers is not None:
            instance.correct_option = ",".join(answers)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance

# ================= EXAM (MCQ ONLY) ================= #

class ExamSerializer(serializers.ModelSerializer):
    # ✅ READ + WRITE (IMPORTANT)
    questions = serializers.PrimaryKeyRelatedField(
        queryset=Question.objects.all(),
        many=True,
        required=False
    )

    subject_id = serializers.IntegerField(source="subject.id", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    question_count = serializers.SerializerMethodField(read_only=True)
    question_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Exam
        fields = [
            "id",
            "title",

            # subject
            "subject",
            "subject_id",
            "subject_name",

            # config
            "duration",
            "mode",

            # questions
            "questions",          # ✅ FIX
            "question_details",
            "question_count",

            # meta
            "is_published",
            "created_at",
        ]

    def get_question_count(self, obj):
        return obj.questions.count()

    def get_question_details(self, obj):
        return QuestionSerializer(obj.questions.all(), many=True).data

    def validate_questions(self, value):
        if len(value) > 100:
            raise serializers.ValidationError(
                "Maximum 100 questions allowed in an exam."
            )
        return value

    def create(self, validated_data):
        questions = validated_data.pop("questions", [])
        exam = Exam.objects.create(**validated_data)
        exam.questions.set(questions)
        return exam

    def update(self, instance, validated_data):
        questions = validated_data.pop("questions", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if questions is not None:
            instance.questions.set(questions)

        return instance
    

class ExamSessionSerializer(serializers.ModelSerializer):
    exam = ExamSerializer(read_only=True)
    exam_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ExamSession
        fields = [
            "id",
            "exam",
            "exam_id",
            "start_time",
            "end_time",
            "is_completed",
        ]
        read_only_fields = [
            "id",
            "exam",
            "start_time",
            "end_time",
            "is_completed",
        ]

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        exam_id = validated_data["exam_id"]

        exam = Exam.objects.get(id=exam_id, is_published=True)

        allowed = StudentSubjectEnrollment.objects.filter(
            student=user,
            subject=exam.subject,
            is_active=True,
        ).exists()

        if not allowed:
            raise serializers.ValidationError({"detail": "Exam not allowed"})

        session, _ = ExamSession.objects.get_or_create(
            student=user,
            exam=exam,
            defaults={"is_completed": False},
        )

        return session

# ================= ANSWER ================= #

class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ['id', 'session', 'question', 'selected_answers']


# ================= RESULT ================= #

class QuestionResultSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    question_text = serializers.CharField()
    correct_answer = serializers.ListField(child=serializers.CharField())
    selected_answer = serializers.ListField(child=serializers.CharField())
    is_correct = serializers.BooleanField()
    marks = serializers.IntegerField()
    earned = serializers.IntegerField()
    explanation = serializers.CharField(allow_null=True)


class ResultSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source="session.exam.title", read_only=True)
    student_name = serializers.CharField(source="session.student.get_full_name", read_only=True)
    student_email = serializers.EmailField(source="session.student.email", read_only=True)
    student_id = serializers.IntegerField(source="session.student.id", read_only=True)

    session_id = serializers.IntegerField(source="session.id", read_only=True)
    submitted_at = serializers.DateTimeField(source="session.end_time", read_only=True)
    date = serializers.DateTimeField(source="session.end_time", read_only=True)

    pass_fail = serializers.SerializerMethodField()
    right_answers = serializers.SerializerMethodField()
    wrong_answers = serializers.SerializerMethodField()
    details = serializers.SerializerMethodField()

    class Meta:
        model = Result
        fields = [
            "id",
            "session_id",
            "exam_title",

            # student info (admin sees all, student sees self)
            "student_id",
            "student_name",
            "student_email",

            "score",
            "total_marks",
            "submitted_at",
            "date",

            "right_answers",
            "wrong_answers",
            "pass_fail",

            "details",
        ]

    def get_pass_fail(self, obj):
        if obj.total_marks == 0:
            return "Fail"
        percent = (obj.score / obj.total_marks) * 100
        return "Pass" if percent >= 80 else "Fail"

    def get_right_answers(self, obj):
        return Answer.objects.filter(
            session=obj.session,
            question__correct_option=models.F("selected_answers")
        ).count()

    def get_wrong_answers(self, obj):
        total = Answer.objects.filter(session=obj.session).count()
        return total - self.get_right_answers(obj)

    def get_details(self, obj):
        answers = Answer.objects.filter(
            session=obj.session
        ).select_related("question")

        data = {}
        for ans in answers:
            q = ans.question

            correct = q.correct_option if isinstance(q.correct_option, list) else [q.correct_option]
            selected = ans.selected_answers if isinstance(ans.selected_answers, list) else [ans.selected_answers]

            is_correct = set(correct) == set(selected)
            earned = q.marks if is_correct else 0

            data[str(q.id)] = {
                "question_text": q.text,
                "correct": correct,
                "selected": selected,
                "is_correct": is_correct,
                "marks": q.marks,
                "earned": earned,
                "explanation": None if is_correct else q.explanation,
            }

        return data