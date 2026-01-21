import requests
import logging

logger = logging.getLogger(__name__)

FASTAPI_VM_URL = "http://127.0.0.1:9000"


def start_vm(snapshot_name: str, email: str):
    payload = {
        "snapshot": snapshot_name,
        "username": email,
    }

    try:
        res = requests.post(
            f"{FASTAPI_VM_URL}/vm/start",
            json=payload,
            timeout=60
        )

        if res.status_code != 200:
            logger.error("VM START FAILED: %s", res.text)
            raise Exception("VM service error")

        return res.json()

    except requests.exceptions.ConnectionError:
        raise Exception("VM service not running")

    except requests.exceptions.Timeout:
        raise Exception("VM start timeout")


def verify_vm(vm_ip, command, expected):
    try:
        res = requests.post(
            f"{FASTAPI_VM_URL}/vm/verify",
            json={
                "vm_ip": vm_ip,
                "command": command,
                "expected": expected
            },
            timeout=20
        )
        return res.json()
    except Exception:
        return {"success": False}


def destroy_vm(vm_name):
    try:
        requests.post(
            f"{FASTAPI_VM_URL}/vm/destroy",
            json={"vm_name": vm_name},
            timeout=20
        )
    except Exception:
        pass

