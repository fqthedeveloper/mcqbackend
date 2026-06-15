import json

from django.http import Http404
from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import (
    IsAuthenticated,
    IsAdminUser
)
from rest_framework.response import Response
from rest_framework import status

from .models import (
    CyberPracticalTask,
    CyberSession,
    CyberMachineSession,
    CyberTopology,
    CyberMachineTemplate,
    CyberEventLog,
)

from .serializers import (
    CyberPracticalTaskSerializer,
    CyberSessionSerializer,
    CyberTopologySerializer,
    CyberMachineTemplateSerializer,
)

from .topology_engine import build_lab_topology

from .services import (
    create_lab,
    verify_lab,
    destroy_lab,
)

from .utils import (
    calculate_session_remaining_time,
    build_machine_switch_payload,
    generate_exam_overview,
)

from .random_credentials import (
    generate_username,
    generate_password,
)

from django.db import transaction


# =========================================================
# ADMIN - MACHINE TEMPLATE
# =========================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_machine_templates(request):

    if request.method == "GET":

        queryset = CyberMachineTemplate.objects.all().order_by("-id")

        serializer = CyberMachineTemplateSerializer(
            queryset,
            many=True
        )

        return Response(serializer.data)

    serializer = CyberMachineTemplateSerializer(
        data=request.data
    )

    serializer.is_valid(raise_exception=True)

    serializer.save()

    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED
    )


# =========================================================
# ADMIN - TOPOLOGY
# =========================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_topologies(request):

    if request.method == "GET":

        queryset = CyberTopology.objects.all().order_by("-id")

        serializer = CyberTopologySerializer(
            queryset,
            many=True
        )

        return Response(serializer.data)

    serializer = CyberTopologySerializer(
        data=request.data
    )

    serializer.is_valid(raise_exception=True)

    serializer.save()

    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED
    )


# =========================================================
# ADMIN - TASKS
# =========================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_tasks(request):

    if request.method == "GET":

        queryset = CyberPracticalTask.objects.all().order_by("-id")

        serializer = CyberPracticalTaskSerializer(
            queryset,
            many=True
        )

        return Response(serializer.data)

    serializer = CyberPracticalTaskSerializer(
        data=request.data
    )

    serializer.is_valid(raise_exception=True)

    serializer.save()

    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED
    )


# =========================================================
# ADMIN - TASK UPDATE
# =========================================================

@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_task_detail(request, pk):

    try:
        task = CyberPracticalTask.objects.get(pk=pk)

    except CyberPracticalTask.DoesNotExist:
        raise Http404("Task not found")

    if request.method == "GET":

        serializer = CyberPracticalTaskSerializer(task)

        return Response(serializer.data)

    if request.method == "PUT":

        serializer = CyberPracticalTaskSerializer(
            task,
            data=request.data,
            partial=True
        )

        serializer.is_valid(raise_exception=True)

        serializer.save()

        return Response(serializer.data)

    task.delete()

    return Response(
        {"message": "Deleted"},
        status=status.HTTP_204_NO_CONTENT
    )


# =========================================================
# STUDENT - LIST TASKS
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_task_list(request):

    queryset = CyberPracticalTask.objects.filter(
        is_active=True,
        is_published=True
    ).order_by("-id")

    serializer = CyberPracticalTaskSerializer(
        queryset,
        many=True
    )

    return Response(serializer.data)


# =========================================================
# STUDENT - TASK DETAIL
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_task_detail(request, pk):

    try:
        task = CyberPracticalTask.objects.get(
            pk=pk,
            is_active=True,
            is_published=True
        )

    except CyberPracticalTask.DoesNotExist:
        raise Http404("Task not found")

    serializer = CyberPracticalTaskSerializer(task)

    return Response(serializer.data)


# =========================================================
# START CYBER PRACTICAL
# =========================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_cyber_practical(request, pk):

    try:

        task = CyberPracticalTask.objects.get(

            pk=pk,

            is_active=True,

            is_published=True
        )

    except CyberPracticalTask.DoesNotExist:

        raise Http404(
            "Task not found"
        )

    # =====================================================
    # THREAD SAFE SESSION LOCK
    # =====================================================

    with transaction.atomic():

        existing = (

            CyberSession.objects

            .select_for_update()

            .filter(

                user=request.user,

                status__in=[
                    "starting",
                    "running"
                ]
            )

            .first()
        )

        if existing:

            return Response(

                {
                    "error":
                        "Exam already running"
                },

                status=400
            )

        # =================================================
        # CREATE SESSION
        # =================================================

        session = CyberSession.objects.create(

            user=request.user,

            task=task,

            status="starting"
        )

    # =====================================================
    # BUILD TOPOLOGY
    # =====================================================

    try:

        topology = build_lab_topology(
            task
        )

        session.variables = (
            topology["variables"]
        )

        session.save()

    except Exception as e:

        session.status = "failed"

        session.save()

        return Response(

            {
                "error":
                    f"Topology build failed: {str(e)}"
            },

            status=500
        )

    # =====================================================
    # START CYBER LAB
    # =====================================================

    try:
        
        attacker_username = generate_username()
        attacker_password = generate_password()

        victim_username = generate_username()
        victim_password = generate_password()

        monitor_username = generate_username()
        monitor_password = generate_password()

        result = create_lab({

            "task_id":
                task.id,

            "session_id":
                session.id,

            "variables":
                topology["variables"],

            "attacker_username":
                attacker_username,

            "attacker_password":
                attacker_password,

            "victim_username":
                victim_username,

            "victim_password":
                victim_password,

            "monitor_username":
                monitor_username,

            "monitor_password":
                monitor_password,

            "attacker_script":
                topology["attacker_script"],

            "victim_script":
                topology["victim_script"],

            "monitor_script":
                topology["monitor_script"],

            "verify_script":
                topology["verify_script"],
        })
        print("\n" + "=" * 80)
        print("FASTAPI RESULT")
        print(json.dumps(result, indent=4))
        print("=" * 80 + "\n")

    except Exception as e:

        session.status = "failed"

        session.save()

        return Response(

            {
                "error":
                    str(e)
            },

            status=500
        )

    # =====================================================
    # GET MACHINE TEMPLATES
    # =====================================================

    attacker_template = (
        task.topology.attacker_template
    )

    victim_template = (
        task.topology.victim_template
    )

    monitor_template = (
        task.topology.monitor_template
    )

    # =====================================================
    # SAVE MACHINE SESSIONS
    # =====================================================

    try:

        attacker_template = getattr(
            task.topology,
            "attacker_template",
            None
        )

        victim_template = getattr(
            task.topology,
            "victim_template",
            None
        )

        monitor_template = getattr(
            task.topology,
            "monitor_template",
            None
        )

        for machine in result.get("machines", []):

            role = machine.get("role")

            if role == "attacker":
                selected_template = attacker_template
            elif role == "victim":
                selected_template = victim_template
            elif role == "monitor":
                selected_template = monitor_template
            else:
                continue

            obj = CyberMachineSession.objects.create(
                session=session,
                role=role,
                template=selected_template,
                vm_name=machine.get("vm_name", ""),
                vm_ip=machine.get("vm_ip"),
                generated_username=machine.get("username", ""),
                generated_password=machine.get("password", ""),
                guacamole_connection_id=str(
                    machine.get("guacamole_connection_id", "")
                ),
                guacamole_url=machine.get("guacamole_url", ""),
                status="running"
            )

            print(
                f"SAVED MACHINE => {obj.id} "
                f"{obj.role} "
                f"{obj.vm_name}"
            )

            CyberMachineSession.objects.create(

                session=session,

                role=role,

                template=selected_template,

                vm_name=machine.get(
                    "vm_name",
                    ""
                ),

                vm_ip=machine.get(
                    "vm_ip",
                    None
                ),

                generated_username=machine.get(
                    "username",
                    ""
                ),

                generated_password=machine.get(
                    "password",
                    ""
                ),

                guacamole_connection_id=machine.get(
                    "guacamole_connection_id",
                    ""
                ),

                guacamole_url=machine.get(
                    "guacamole_url",
                    ""
                ),

                status="running"
            )

    except Exception as e:

        import traceback

        traceback.print_exc()

        session.status = "failed"
        session.save()

        return Response(
            {
                "error": str(e),
                "type": type(e).__name__
            },
            status=500
        )

    # =====================================================
    # UPDATE SESSION
    # =====================================================

    session.status = "running"

    session.save()

    # =====================================================
    # LOG EVENT
    # =====================================================

    CyberEventLog.objects.create(

        session=session,

        event_type="start",

        data={

            "task_id":
                task.id,

            "task_title":
                task.title,

            "machines":
                result.get(
                    "machines",
                    []
                )
        }
    )

    # =====================================================
    # RESPONSE
    # =====================================================

    serializer = CyberSessionSerializer(
        session
    )

    return Response(

        serializer.data,

        status=200
    )
    
    
# =========================================================
# RESUME SESSION
# =========================================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_active_cyber_session(request):

    session = (
        CyberSession.objects
        .filter(
            user=request.user
        )
        .exclude(
            status__in=[
                "submitted",
                "destroyed"
            ]
        )
        .order_by("-id")
        .first()
    )

    if not session:
        return Response({
            "active": False
        })

    machines = []

    for machine in session.machines.all():

        machines.append({
            "id": machine.id,
            "role": machine.role,
            "vm_name": machine.vm_name,
            "vm_ip": machine.vm_ip,
            "username": machine.generated_username,
            "password": machine.generated_password,
            "status": machine.status,
            "guacamole_url": machine.guacamole_url,
        })

    serializer = CyberSessionSerializer(session)

    return Response({
        "active": True,
        "session": serializer.data,
        "machines": machines
    })


# =========================================================
# GET SESSION
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_session(request, pk):

    try:

        session = CyberSession.objects.get(

            pk=pk,

            user=request.user
        )

    except CyberSession.DoesNotExist:

        raise Http404(
            "Session not found"
        )

    serializer = CyberSessionSerializer(
        session
    )

    remaining_time = (
        calculate_session_remaining_time(
            session
        )
    )

    switcher = (
        build_machine_switch_payload(
            session
        )
    )

    overview = (
        generate_exam_overview(
            session
        )
    )

    machines = []

    for machine in session.machines.all():

        machines.append({

            "id":
                machine.id,

            "role":
                machine.role,

            "vm_name":
                machine.vm_name,

            "vm_ip":
                machine.vm_ip,

            "username":
                machine.generated_username,

            "password":
                machine.generated_password,

            "status":
                machine.status,

            "guacamole_url":
                machine.guacamole_url,
        })

    return Response({

        "session":
            serializer.data,

        "remaining_time":
            remaining_time,

        "machine_switcher":
            switcher,

        "overview":
            overview,

        "machines":
            machines,
    })


# =========================================================
# SUBMIT SESSION
# =========================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_session(request, pk):

    try:
        session = CyberSession.objects.get(
            pk=pk,
            user=request.user,
            status="running"
        )

    except CyberSession.DoesNotExist:
        raise Http404("Session not found")

    verify_result = verify_lab({

        "session_id": session.id,

        "variables": session.variables,
    })

    session.obtained_marks = verify_result.get(
        "score",
        0
    )

    session.verification_output = verify_result.get(
        "raw_output",
        ""
    )

    session.verification_details = verify_result.get(
        "details",
        []
    )

    session.calculate_percentage()

    session.is_passed = session.percentage >= 50

    session.status = "submitted"

    session.end_time = timezone.now()

    session.save()

    destroy_lab({
        "session_id": session.id
    })

    return Response({
        "score": session.obtained_marks,
        "percentage": session.percentage,
        "passed": session.is_passed,
    })


# =========================================================
# STUDENT RESULTS
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_results(request):

    queryset = CyberSession.objects.filter(
        user=request.user
    ).order_by("-id")

    serializer = CyberSessionSerializer(
        queryset,
        many=True
    )

    return Response(serializer.data)


# =========================================================
# ADMIN RESULTS
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_results(request):

    queryset = CyberSession.objects.all().order_by("-id")

    serializer = CyberSessionSerializer(
        queryset,
        many=True
    )

    return Response(serializer.data)