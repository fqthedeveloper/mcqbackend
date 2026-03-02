import requests
import logging
import time
from typing import Dict, Any, Optional

from practicalapp.models import PracticalSession

logger = logging.getLogger(__name__)

FASTAPI_VM_URL = "http://127.0.0.1:9000"

VM_VERIFY_TIMEOUT = 300
VM_DESTROY_TIMEOUT = 300
VM_STATUS_TIMEOUT = 900          # 15 minutes max wait
VM_STATUS_POLL_INTERVAL = 5      # seconds


# ==========================================
# START VM (NON BLOCKING + POLLING)
# ==========================================
def start_vm(task, user_email=None):

    try:
        # STEP 1: Ask FastAPI to start VM (non-blocking)
        response = requests.post(
            f"{FASTAPI_VM_URL}/vm/start",
            json={"init_script": task.init_script},
            timeout=60
        )

        response.raise_for_status()
        data = response.json()

        vm_name = data.get("vm_name")

        if not vm_name:
            raise Exception("VM name not returned")

        # STEP 2: Poll for status
        start_time = time.time()

        while time.time() - start_time < VM_STATUS_TIMEOUT:

            status_response = requests.get(
                f"{FASTAPI_VM_URL}/vm/status/{vm_name}",
                timeout=30
            )

            status_response.raise_for_status()
            status_data = status_response.json()

            status = status_data.get("status")

            if status == "running":
                return {
                    "vm_name": vm_name,
                    "vm_ip": status_data.get("vm_ip"),
                    "username": status_data.get("username"),
                    "password": status_data.get("password"),
                }

            if status == "failed":
                raise Exception(status_data.get("error", "VM failed"))

            time.sleep(VM_STATUS_POLL_INTERVAL)

        raise Exception("VM start timeout")

    except Exception as e:
        logger.exception("VM start failed")
        return {
            "error": str(e)
        }

# ==========================================
# VERIFY VM
# ==========================================
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


# ==========================================
# DESTROY VM
# ==========================================
def destroy_vm_remote(session: PracticalSession):

    if not session.vm_name:
        logger.error("Destroy skipped — vm_name empty for session %s", session.id)
        return None

    try:
        response = requests.post(
            f"{FASTAPI_VM_URL}/vm/destroy",
            json={"vm_name": session.vm_name},
            timeout=VM_DESTROY_TIMEOUT
        )

        response.raise_for_status()
        data = response.json()

        return data.get("history_path")

    except requests.RequestException as e:
        logger.error("VM destroy error: %s", str(e))
        return None