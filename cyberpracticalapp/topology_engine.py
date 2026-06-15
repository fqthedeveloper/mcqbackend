import random

from .variable_engine import generate_variables
from .render import render_template


# =========================================================
# BUILD MACHINE PAYLOAD
# =========================================================

def build_machine_payload(
    template,
    role
):

    return {

        "template_id": template.id,

        "role": role,

        "vm_name":
            f"{role}-{random.randint(1000,9999)}",

        "base_box":
            template.base_box,

        "memory_mb":
            template.memory_mb,

        "cpu_count":
            template.cpu_count,

        "gui_enabled":
            template.gui_enabled,

        "os_type":
            getattr(
                template,
                "os_type",
                "linux"
            ),

        "username":
            getattr(
                template,
                "default_username",
                "vagrant"
            ),

        "password":
            getattr(
                template,
                "default_password",
                "vagrant"
            ),

        "extra_disk_gb":
            getattr(
                template,
                "extra_disk_gb",
                0
            ),

        "ip": None,
    }


# =========================================================
# BUILD FULL LAB TOPOLOGY
# =========================================================

def build_lab_topology(task):

    variables = generate_variables(
        task.variable_schema
    )

    topology = task.topology

    attacker_machine = build_machine_payload(

        topology.attacker_template,

        "attacker"
    )

    victim_machine = build_machine_payload(

        topology.victim_template,

        "victim"
    )

    monitor_machine = None

    if topology.monitor_template:

        monitor_machine = build_machine_payload(

            topology.monitor_template,

            "monitor"
        )

    # =====================================================
    # RENDER INIT SCRIPTS
    # =====================================================

    attacker_script = render_template(

        task.attacker_init_template,

        variables
    )

    victim_script = render_template(

        task.victim_init_template,

        variables
    )

    monitor_script = render_template(

        task.monitor_init_template or "",

        variables
    )

    verify_script = render_template(

        task.verify_template,

        variables
    )

    payload = {

        "variables": {

            "attacker":
                attacker_machine,

            "victim":
                victim_machine,
        },

        "attacker_script":
            attacker_script,

        "victim_script":
            victim_script,

        "monitor_script":
            monitor_script,

        "verify_script":
            verify_script,
    }

    if monitor_machine:

        payload["variables"]["monitor"] = (
            monitor_machine
        )

    return payload