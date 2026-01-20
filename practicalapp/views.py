from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django.utils import timezone
from rest_framework import status

from .models import PracticalTask, PracticalSession
from .services import start_vm, verify_vm, destroy_vm
from .serializers import PracticalTaskSerializer
from mcqapp.models import Subject


# ================================
# ADMIN: LIST + CREATE
# ================================
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAdminUser])
def practical_task_list_create(request):
    if request.method == "GET":
        tasks = PracticalTask.objects.select_related("subject").all().order_by("-id")
        serializer = PracticalTaskSerializer(tasks, many=True)
        return Response(serializer.data)

    if request.method == "POST":
        serializer = PracticalTaskSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ================================
# ADMIN: UPDATE
# ================================
@api_view(["PUT"])
@permission_classes([IsAuthenticated, IsAdminUser])
def practical_task_update(request, pk):
    try:
        task = PracticalTask.objects.get(pk=pk)
    except PracticalTask.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)

    serializer = PracticalTaskSerializer(task, data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def available_practicals(request):
    if request.user.user_type != "student":
        return Response({"detail": "Forbidden"}, status=403)

    subjects = Subject.objects.filter(is_active=True)

    tasks = PracticalTask.objects.filter(
        subject__in=subjects,
        is_published=True,
        is_active=True,
    )

    serializer = PracticalTaskSerializer(tasks, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_practical(request):
    if request.user.user_type != "student":
        return Response({"detail": "Forbidden"}, status=403)

    task_id = request.data.get("task_id")

    try:
        task = PracticalTask.objects.get(
            id=task_id, is_published=True, is_active=True
        )
    except PracticalTask.DoesNotExist:
        return Response({"error": "Practical not available"}, status=404)

    if PracticalSession.objects.filter(user=request.user, status="running").exists():
        return Response({"error": "Already running"}, status=400)

    vm_data = start_vm(task.snapshot_name, request.user.email)

    session = PracticalSession.objects.create(
        user=request.user,
        task=task,
        vm_name=vm_data["vm_name"],
        vm_ip=vm_data["vm_ip"],
    )

    return Response(
        {
            "task": task.title,
            "subject": task.subject.name,
            "vm_ip": session.vm_ip,
            "ssh_user": "student",
            "ssh_password": "student",
            "time_minutes": task.duration_minutes,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_practical(request):
    session = PracticalSession.objects.get(
        user=request.user, status="running"
    )

    result = verify_vm(
        session.vm_ip,
        session.task.verify_command,
        session.task.expected_output,
    )

    session.obtained_marks = (
        session.task.total_marks if result["success"] else 0
    )
    session.calculate_percentage()
    session.status = "submitted"
    session.end_time = timezone.now()
    session.save()

    destroy_vm(session.vm_name)

    return Response(
        {
            "marks": session.obtained_marks,
            "total_marks": session.task.total_marks,
            "percentage": session.percentage,
        }
    )
