from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django.utils import timezone
from rest_framework import status
from mcqapp.models import StudentSubjectEnrollment
from django.db import transaction
from .models import PracticalTask, PracticalSession
from .serializers import PracticalTaskSerializer
from .services import start_vm, verify_vm, destroy_vm
from mcqapp.models import Subject


# ================= ADMIN =================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_practical_list_create(request):
    if request.method == "GET":
        tasks = PracticalTask.objects.select_related("subject").all()
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


# ================= STUDENT =================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_practical_list(request):
    user = request.user

    if user.user_type != "student":
        return Response({"detail": "Forbidden"}, status=403)

    # ================= GET STUDENT SUBJECTS (CORRECT WAY) =================
    subject_ids = StudentSubjectEnrollment.objects.filter(
        student=user,
        is_active=True
    ).values_list("subject_id", flat=True)

    if not subject_ids.exists():
        # Student is not enrolled in any subject
        return Response([])

    # ================= GET PRACTICAL TASKS =================
    tasks = PracticalTask.objects.filter(
        subject_id__in=subject_ids,
        is_active=True,
        is_published=True
    ).select_related("subject")

    data = []
    for task in tasks:
        session = PracticalSession.objects.filter(
            user=user,
            task=task
        ).order_by("-id").first()

        data.append({
            "task_id": task.id,
            "title": task.title,
            "subject": task.subject.name,
            "duration": task.duration_minutes,
            "status": session.status if session else "not_started"
        })

    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_practical_detail(request, pk):
    task = PracticalTask.objects.get(pk=pk)
    return Response(PracticalTaskSerializer(task).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_practical_start(request, pk):
    user = request.user

    with transaction.atomic():
        if PracticalSession.objects.select_for_update().filter(
            user=user, status="running"
        ).exists():
            return Response(
                {"error": "Another practical already running"},
                status=400
            )

        task = PracticalTask.objects.get(
            pk=pk,
            is_active=True,
            is_published=True
        )

        # TEMP VM NAME (will be overwritten)
        session = PracticalSession.objects.create(
            user=user,
            task=task,
            vm_name=f"pending-{user.id}-{pk}",
            status="starting"
        )

    # VM START (OUTSIDE TRANSACTION)
    vm = start_vm(task.snapshot_name, user.email)

    session.vm_name = vm["vm_name"]
    session.vm_ip = vm["vm_ip"]
    session.status = "running"
    session.save()

    return Response({
        "session_id": session.id,
        "vm_ip": session.vm_ip,
        "duration": task.duration_minutes
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def practical_session_detail(request, pk):
    session = PracticalSession.objects.get(pk=pk, user=request.user)

    return Response({
        "id": session.id,
        "task_id": session.task.id,
        "title": session.task.title,
        "description": session.task.description,
        "duration": session.task.duration_minutes,
        "start_time": session.start_time,
        "status": session.status,
        "vm_ip": session.vm_ip,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def practical_session_submit(request, pk):
    session = PracticalSession.objects.get(pk=pk, user=request.user, status="running")

    result = verify_vm(
        session.vm_ip,
        session.task.verify_command,
        session.task.expected_output,
    )

    session.obtained_marks = session.task.total_marks if result["success"] else 0
    session.calculate_percentage()
    session.status = "submitted"
    session.end_time = timezone.now()
    session.save()

    destroy_vm(session.vm_name)

    return Response({
        "marks": session.obtained_marks,
        "total_marks": session.task.total_marks,
        "percentage": session.percentage,
    })
