import requests
import logging
from typing import Dict, Any, Optional

from practicalapp.models import PracticalSession

logger = logging.getLogger(__name__)

# ============================
# CONFIG
# ============================
FASTAPI_VM_URL = "http://127.0.0.1:9000"

# Hard limits (seconds)
VM_START_TIMEOUT = 600      # 10 minutes (VM boot can be slow)
VM_VERIFY_TIMEOUT = 300
VM_DESTROY_TIMEOUT = 300


# ============================
# START VM
# ============================
def start_vm(task, user_email: Optional[str] = None) -> Dict[str, Any]:
    
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


# ============================
# VERIFY VM (SAFE VERSION)
# ============================

def verify_vm(vm_ip: str, verify_script: str):

    if not vm_ip:
        return {
            "score": 0,
            "raw_output": "VM IP not available",
            "details": []
        }

    try:
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

        return {
            "score": data.get("score", 0),
            "raw_output": data.get("raw_output", ""),
            "details": data.get("details", [])
        }

    except requests.Timeout:
        return {
            "score": 0,
            "raw_output": "Verification timeout",
            "details": []
        }

    except requests.RequestException as e:
        return {
            "score": 0,
            "raw_output": f"FastAPI error: {str(e)}",
            "details": []
        }


# ============================
# DESTROY VM REMOTE (SAFE)
# ============================

def destroy_vm_remote(session: PracticalSession):

    if not session.vm_name:
        logger.error("Destroy skipped — vm_name is empty for session %s", session.id)
        return None

    logger.info("Destroying VM | session=%s vm_name=%s",
                session.id, session.vm_name)

    try:
        response = requests.post(
            f"{FASTAPI_VM_URL}/vm/destroy",
            json={"vm_name": session.vm_name},
            timeout=VM_DESTROY_TIMEOUT
        )

        response.raise_for_status()
        data = response.json()

        logger.info("Destroy response: %s", data)

        history_path = data.get("history_path")

        if history_path:
            session.history_path = history_path
            session.save(update_fields=["history_path"])

        return history_path

    except requests.Timeout:
        logger.error("VM destroy timeout for session %s", session.id)
        return None

    except requests.RequestException as e:
        logger.error("VM destroy error: %s", str(e))
        return None