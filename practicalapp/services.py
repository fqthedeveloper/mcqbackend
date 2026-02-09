import requests
import logging

logger = logging.getLogger(__name__)

FASTAPI_VM_URL = "http://127.0.0.1:9000"


def start_vm(task, user_email):
    payload = {
        "init_script": task.init_script
    }

    try:
        res = requests.post(
            f"{FASTAPI_VM_URL}/vm/start",
            json=payload,
            timeout=600  # ⏱ 10 minutes (REQUIRED)
        )
        res.raise_for_status()
        return res.json()

    except requests.exceptions.ReadTimeout:
        logger.error("VM provisioning timed out (still booting)")
        return {
            "error": "VM provisioning timeout",
            "detail": "VM is still starting, please wait"
        }

    except requests.exceptions.RequestException as e:
        logger.exception("VM service error")
        return {
            "error": "VM service unreachable",
            "detail": str(e)
        }


def verify_vm(vm_ip, verify_script):
    res = requests.post(
        f"{FASTAPI_VM_URL}/vm/verify",
        json={
            "vm_ip": vm_ip,
            "script": verify_script
        },
        timeout=60
    )
    res.raise_for_status()
    return res.json()


def destroy_vm(vm_name):
    try:
        requests.post(
            f"{FASTAPI_VM_URL}/vm/destroy",
            json={"vm_name": vm_name},
            timeout=60
        )
    except requests.exceptions.RequestException:
        logger.warning("Failed to notify VM destroy")
