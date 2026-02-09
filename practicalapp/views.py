# practicalapp/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django.utils import timezone
from django.db import transaction, IntegrityError

from .models import PracticalTask, PracticalSession
from .serializers import PracticalTaskSerializer
from .services import start_vm, verify_vm, destroy_vm
from mcqapp.models import StudentSubjectEnrollment


# ============================
# ADMIN
# ============================
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_practical_list_create(request):
    if request.method == "GET":
        tasks = PracticalTask.objects.all()
        return Response(PracticalTaskSerializer(tasks, many=True).data)

    serializer = PracticalTaskSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=201)


@api_view(["PUT"])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_practical_update(request, pk):
    task = PracticalTask.objects.get(pk=pk)
    serializer = PracticalTaskSerializer(task, data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


# ============================
# STUDENT PRACTICAL LIST
# ============================
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


# ============================
# TASK DETAIL (RULES PAGE)
# ============================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_practical_detail(request, pk):
    task = PracticalTask.objects.get(
        pk=pk,
        is_active=True,
        is_published=True
    )

    return Response({
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "duration": task.duration_minutes,
        "total_marks": task.total_marks,
    })


# ============================
# START PRACTICAL
# ============================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_practical_start(request, pk):
    user = request.user

    # 🔒 RETURN EXISTING SESSION IF RUNNING
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

    with transaction.atomic():
        task = PracticalTask.objects.get(
            pk=pk,
            is_active=True,
            is_published=True
        )

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
        return Response({"error": "VM provisioning failed"}, status=500)

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



# ============================
# GET SESSION (FIXES undefined)
# ============================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_practical_session(request, pk):
    session = PracticalSession.objects.get(
        pk=pk,
        user=request.user
    )

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


# ============================
# SUBMIT PRACTICAL
# ============================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def practical_session_submit(request, pk):
    session = PracticalSession.objects.get(
        pk=pk,
        user=request.user,
        status="running"
    )

    result = verify_vm(
        session.vm_ip,
        session.task.verify_script
    )

    score = 0
    for line in result["output"].splitlines():
        if line.startswith("SCORE="):
            score = int(line.split("=")[1])

    session.obtained_marks = score
    session.calculate_percentage()
    session.status = "submitted"
    session.end_time = timezone.now()
    session.save()

    destroy_vm(session.vm_name)

    return Response({
        "marks": session.obtained_marks,
        "total_marks": session.task.total_marks,
        "percentage": session.percentage
    })
