from django.utils import timezone


# =========================================================
# SESSION REMAINING TIME
# =========================================================

def calculate_session_remaining_time(session):

    if not session.start_time:
        return 0

    total_seconds = (
        session.task.duration_minutes * 60
    )

    elapsed = (
        timezone.now() - session.start_time
    ).total_seconds()

    remaining = int(total_seconds - elapsed)

    if remaining < 0:
        remaining = 0

    return remaining


# =========================================================
# MACHINE SWITCH PAYLOAD
# =========================================================

def build_machine_switch_payload(session):

    payload = []

    for machine in session.machines.all():

        payload.append({

            "role": machine.role,

            "vm_name": machine.vm_name,

            "vm_ip": machine.vm_ip,

            "status": machine.status,

            "guacamole_url": machine.guacamole_url,

            "connection_id": machine.guacamole_connection_id,
        })

    return payload


# =========================================================
# EXAM OVERVIEW
# =========================================================

def generate_exam_overview(session):

    return {

        "title": session.task.title,

        "description": session.task.description,

        "difficulty": session.task.difficulty,

        "total_marks": session.task.total_marks,

        "duration_minutes": session.task.duration_minutes,

        "topology": session.task.topology.name,

        "machine_count": session.machines.count(),

        "started_at": session.start_time,
    }


# =========================================================
# FORMAT TIMER
# =========================================================

def format_seconds(seconds):

    hours = seconds // 3600

    minutes = (seconds % 3600) // 60

    secs = seconds % 60

    return  f'{hours:02d}:{minutes:02d}:{secs:02d}'


# =========================================================
# DETECT SESSION EXPIRY
# =========================================================

def is_session_expired(session):

    remaining = calculate_session_remaining_time(
        session
    )

    return remaining <= 0


# =========================================================
# BUILD FRONTEND MACHINE TABS
# =========================================================

def build_machine_tabs(session):

    tabs = []

    for machine in session.machines.all():

        tabs.append({

            "label": machine.role.capitalize(),

            "role": machine.role,

            "active": machine.role == "attacker",

            "guacamole_url": machine.guacamole_url,
        })

    return tabs


# =========================================================
# BUILD LIVE EXAM HEADER
# =========================================================

def build_exam_header(session):

    return {

        "exam_title": session.task.title,

        "subject": session.task.subject.name,

        "difficulty": session.task.difficulty,

        "status": session.status,

        "remaining_time": calculate_session_remaining_time(
            session
        ),
    }