from celery import shared_task

from .models import (
    CyberMachineSession
)

from .services import (
    create_lab
)


@shared_task
def async_start_machine(
    machine_session_id,
    payload
):

    machine = CyberMachineSession.objects.get(
        id=machine_session_id
    )

    try:

        result = create_lab(payload)

        machine.vm_name = result["vm_name"]

        machine.vm_ip = result["vm_ip"]

        machine.username = result["username"]

        machine.password = result["password"]

        machine.guacamole_url = result[
            "guacamole_url"
        ]

        machine.status = "running"

        machine.save()

    except Exception:

        machine.status = "failed"

        machine.save()