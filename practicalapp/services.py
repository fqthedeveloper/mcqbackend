import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ============================
# CONFIG
# ============================
FASTAPI_VM_URL = "http://127.0.0.1:9000"

# Hard limits (seconds)
VM_START_TIMEOUT = 600      # 10 minutes (VM boot can be slow)
VM_VERIFY_TIMEOUT = 60
VM_DESTROY_TIMEOUT = 60


# ============================
# START VM
# ============================
def start_vm(task, user_email: Optional[str] = None) -> Dict[str, Any]:
    """
    Calls FastAPI VM service to start a VM.

    IMPORTANT:
    - This function MAY BLOCK for several minutes.
    - It MUST be called from a background thread.
    """

    payload = {
        "init_script": task.init_script
    }

    # Optional metadata (safe to ignore on VM side)
    if user_email:
        payload["user_email"] = user_email

    logger.info(
        "Requesting VM start | task_id=%s user=%s",
        getattr(task, "id", None),
        user_email,
    )

    try:
        response = requests.post(
            f"{FASTAPI_VM_URL}/vm/start",
            json=payload,
            timeout=VM_START_TIMEOUT
        )

        response.raise_for_status()

        data = response.json()

        # Basic validation
        if not isinstance(data, dict):
            raise ValueError("Invalid response format from VM service")

        if "vm_ip" not in data or "vm_name" not in data:
            raise ValueError(f"Incomplete VM response: {data}")

        logger.info(
            "VM started successfully | vm_name=%s vm_ip=%s",
            data.get("vm_name"),
            data.get("vm_ip"),
        )

        return data

    except requests.exceptions.ReadTimeout:
        logger.error(
            "VM provisioning timed out (VM may still be booting in background)"
        )
        return {
            "error": "VM provisioning timeout",
            "detail": "VM is still starting, please wait"
        }

    except requests.exceptions.ConnectionError as e:
        logger.exception("VM service connection failed")
        return {
            "error": "VM service unreachable",
            "detail": str(e)
        }

    except requests.exceptions.HTTPError as e:
        logger.exception("VM service returned HTTP error")
        return {
            "error": "VM service error",
            "detail": str(e),
            "status_code": getattr(e.response, "status_code", None),
        }

    except Exception as e:
        logger.exception("Unexpected VM start failure")
        return {
            "error": "Unexpected VM start failure",
            "detail": str(e)
        }

def verify_vm(vm_ip: str, verify_script: str) -> Dict[str, Any]:
    """
    Calls FastAPI VM service to execute verification script.
    """

    logger.info("Verifying VM | vm_ip=%s", vm_ip)

    response = requests.post(
        f"{FASTAPI_VM_URL}/vm/verify",
        json={
            "vm_ip": vm_ip,
            "script": verify_script
        },
        timeout=VM_VERIFY_TIMEOUT
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        raise ValueError("Invalid verify response from VM service")

    return data


# ============================
# DESTROY VM
# ============================
def destroy_vm(vm_name: str) -> str:
    """
    Requests VM destruction and receives history path.
    """

    logger.info("Destroying VM | vm_name=%s", vm_name)

    try:
        response = requests.post(
            f"{FASTAPI_VM_URL}/vm/destroy",
            json={"vm_name": vm_name},
            timeout=VM_DESTROY_TIMEOUT
        )

        data = response.json()

        return data.get("history_path")

    except requests.exceptions.RequestException as e:
        logger.warning(
            "Failed VM destroy | vm_name=%s | error=%s",
            vm_name,
            str(e),
        )
        return None
