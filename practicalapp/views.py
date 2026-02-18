from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db import transaction
from django.http import Http404
from .models import PracticalTask, PracticalSession
from .serializers import PracticalTaskSerializer
from .services import start_vm, verify_vm, destroy_vm_remote
from mcqapp.models import StudentSubjectEnrollment
import os
import logging
from mcqbackend.settings import HISTORY_ROOT



logger = logging.getLogger(__name__)


# ============================================================
# ADMIN - CREATE & LIST PRACTICAL TASKS
# ============================================================
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_practical_list_create(request):

    if request.method == "GET":
        tasks = PracticalTask.objects.all().order_by("-id")
        serializer = PracticalTaskSerializer(tasks, many=True)
        return Response(serializer.data)

    serializer = PracticalTaskSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["PUT"])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_practical_update(request, pk):

    try:
        task = PracticalTask.objects.get(pk=pk)
    except PracticalTask.DoesNotExist:
        raise Http404("Task not found")

    serializer = PracticalTaskSerializer(task, data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


# ============================================================
# STUDENT PRACTICAL LIST
# ============================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_practical_list(request):

    user = request.user

    subject_ids = StudentSubjectEnrollment.objects.filter(
        student=user,
        is_active=True
    ).values_list("subject_id", flat=True)

    tasks = PracticalTask.objects.filter(
        subject_id__in=subject_ids,
        is_active=True,
        is_published=True
    )

    data = []

    for task in tasks:
        session = PracticalSession.objects.filter(
            user=user,
            task=task
        ).order_by("-id").first()

        data.append({
            "task_id": task.id,
            "title": task.title,
            "duration": task.duration_minutes,
            "status": session.status if session else "not_started",
            "session_id": session.id if session else None
        })

    return Response(data)


# ============================================================
# TASK DETAIL (RULES PAGE)
# ============================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_practical_detail(request, pk):

    try:
        task = PracticalTask.objects.get(
            pk=pk,
            is_active=True,
            is_published=True
        )
    except PracticalTask.DoesNotExist:
        raise Http404("Task not found")

    return Response({
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "duration": task.duration_minutes,
        "total_marks": task.total_marks,
    })


# ============================================================
# START PRACTICAL
# ============================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_practical_start(request, pk):

    user = request.user

    # Return existing running session
    existing = PracticalSession.objects.filter(
        user=user,
        status__in=["starting", "running"]
    ).order_by("-id").first()

    if existing:
        return Response({
            "session_id": existing.id,
            "vm_ip": existing.vm_ip,
            "duration": existing.task.duration_minutes,
            "title": existing.task.title,
            "description": existing.task.description
        })

    try:
        task = PracticalTask.objects.get(
            pk=pk,
            is_active=True,
            is_published=True
        )
    except PracticalTask.DoesNotExist:
        raise Http404("Task not found")

    with transaction.atomic():
        session = PracticalSession.objects.create(
            user=user,
            task=task,
            status="starting"
        )

    vm = start_vm(task, user.email)

    if not vm or "vm_ip" not in vm:
        session.status = "failed"
        session.end_time = timezone.now()
        session.save()
        return Response(
            {"error": "VM provisioning failed"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    session.vm_name = vm["vm_name"]
    session.vm_ip = vm["vm_ip"]
    session.status = "running"
    session.save()

    return Response({
        "session_id": session.id,
        "vm_ip": session.vm_ip,
        "duration": task.duration_minutes,
        "title": task.title,
        "description": task.description
    })


# ============================================================
# GET SESSION
# ============================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_practical_session(request, pk):

    try:
        session = PracticalSession.objects.get(
            pk=pk,
            user=request.user
        )
    except PracticalSession.DoesNotExist:
        raise Http404("Session not found")

    task = session.task

    return Response({
        "id": session.id,
        "status": session.status,
        "title": task.title,
        "description": task.description,
        "duration": task.duration_minutes,
        "start_time": session.start_time,
        "vm_ip": session.vm_ip,
    })
    
    
# ========================
# Submit VM
# ========================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def practical_session_submit(request, pk):

    try:
        session = PracticalSession.objects.select_for_update().get(
            pk=pk,
            user=request.user,
            status="running"
        )
    except PracticalSession.DoesNotExist:
        raise Http404("Active session not found")

    # ========================
    # VERIFY
    # ========================
    verify_result = verify_vm(
        session.vm_ip,
        session.task.verify_script
    )

    session.obtained_marks = verify_result.get("score", 0)
    session.verification_output = verify_result.get("raw_output", "")
    session.verification_details = verify_result.get("details", [])
    session.end_time = timezone.now()
    session.status = "submitted"

    session.calculate_percentage()
    session.is_passed = session.percentage >= 50

    session.save()

    # ========================
    # DESTROY VM
    # ========================
    history_path = destroy_vm_remote(session)

    if history_path:
        session.history_path = history_path
        session.save(update_fields=["history_path"])

    return Response({
        "id": session.id,
        "marks": session.obtained_marks,
        "total_marks": session.task.total_marks,
        "percentage": session.percentage,
        "passed": session.is_passed,
        "details": session.verification_details,
        "raw_output": session.verification_output,
        "history_available": bool(session.history_path),
        "submitted_at": session.end_time
    })


# ============================================================
# STUDENT PRACTICAL RESULTS
# ============================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_practical_results(request):

    sessions = PracticalSession.objects.filter(
        user=request.user,
        status="submitted"
    ).order_by("-id")

    data = []

    for s in sessions:
        data.append({
            "id": s.id,
            "student": s.user.email,
            "task_title": s.task.title,
            "marks": s.obtained_marks,
            "total_marks": s.task.total_marks,
            "percentage": s.percentage,
            "vm_name": s.vm_name,
            "submitted_at": s.end_time,
            "verification_details": s.verification_details,
            "verification_output": s.verification_output,
        })

    return Response(data)


# ============================================================
# ADMIN PRACTICAL RESULTS
# ============================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_practical_results(request):

    sessions = PracticalSession.objects.filter(
        status="submitted"
    ).order_by("-id")

    data = []

    for s in sessions:
        data.append({
            "id": s.id,
            "student": s.user.email,
            "task_title": s.task.title,
            "marks": s.obtained_marks,
            "total_marks": s.task.total_marks,
            "percentage": s.percentage,
            "vm_name": s.vm_name,
            "submitted_at": s.end_time,
            "verification_details": s.verification_details,
            "verification_output": s.verification_output,
        })

    return Response(data)


# ============================================================
# RESULT DETAIL (FULL FIXED VERSION)
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def practical_result_detail(request, pk):

    try:
        if request.user.is_staff:
            session = PracticalSession.objects.get(
                pk=pk,
                status="submitted"
            )
        else:
            session = PracticalSession.objects.get(
                pk=pk,
                user=request.user,
                status="submitted"
            )
    except PracticalSession.DoesNotExist:
        raise Http404("Result not found")

    history_files = []

    if session.history_path and os.path.exists(session.history_path):

        for root, dirs, files in os.walk(session.history_path):
            for file in files:
                full_path = os.path.join(root, file)

                relative_path = os.path.relpath(
                    full_path,
                    session.history_path
                )

                history_files.append({
                    "name": relative_path
                })

    return Response({
        "id": session.id,
        "student": session.user.email,
        "task_title": session.task.title,
        "marks": session.obtained_marks,
        "total_marks": session.task.total_marks,
        "percentage": session.percentage,
        "passed": session.is_passed,
        "details": session.verification_details,
        "raw_output": session.verification_output,
        "vm_name": session.vm_name,
        "submitted_at": session.end_time,
        "history_files": history_files
    })


# ============================================================
# READ HISTORY FILE (SECURE)
# ============================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def practical_history_file(request, pk):

    relative_file = request.GET.get("file")

    if not relative_file:
        return Response(
            {"error": "File parameter required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        if request.user.is_staff:
            session = PracticalSession.objects.get(pk=pk)
        else:
            session = PracticalSession.objects.get(
                pk=pk,
                user=request.user
            )
    except PracticalSession.DoesNotExist:
        raise Http404("Session not found")

    if not session.history_path:
        return Response(
            {"error": "History not available"},
            status=status.HTTP_404_NOT_FOUND
        )

    base_path = os.path.abspath(session.history_path)
    requested_path = os.path.abspath(
        os.path.join(base_path, relative_file)
    )

    # SECURITY: Prevent path traversal
    if not requested_path.startswith(base_path):
        return Response(
            {"error": "Invalid file path"},
            status=status.HTTP_403_FORBIDDEN
        )

    if not os.path.exists(requested_path):
        return Response(
            {"error": "File not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        with open(requested_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return Response(
            {"error": "Unable to read file"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return Response({
        "file": relative_file,
        "content": content
    })

# ============================================================
# HISTORY LIST
# ============================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def practical_session_history(request, pk):

    try:
        if request.user.is_staff:
            session = PracticalSession.objects.get(pk=pk)
        else:
            session = PracticalSession.objects.get(
                pk=pk,
                user=request.user
            )
    except PracticalSession.DoesNotExist:
        return Response({"error": "Session not found"}, status=404)

    if not session.history_path:
        return Response({"error": "History not available"}, status=404)

    if not os.path.exists(session.history_path):
        return Response({"error": "History folder missing"}, status=404)

    files = []

    for root, dirs, filenames in os.walk(session.history_path):
        for f in filenames:
            full_path = os.path.join(root, f)
            relative_path = os.path.relpath(
                full_path,
                session.history_path
            )
            files.append({"name": relative_path})

    return Response({
        "id": session.id,
        "history_files": files
    })