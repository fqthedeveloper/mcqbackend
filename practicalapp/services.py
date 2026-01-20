import requests

FASTAPI_BASE_URL = "http://127.0.0.1:9000"


def start_vm(snapshot_name, username):
    res = requests.post(
        f"{FASTAPI_BASE_URL}/vm/start",
        json={"snapshot": snapshot_name, "username": username},
        timeout=30,
    )
    res.raise_for_status()
    return res.json()


def verify_vm(vm_ip, command, expected_output):
    res = requests.post(
        f"{FASTAPI_BASE_URL}/vm/verify",
        json={
            "vm_ip": vm_ip,
            "command": command,
            "expected": expected_output,
        },
        timeout=30,
    )
    res.raise_for_status()
    return res.json()


def destroy_vm(vm_name):
    res = requests.post(
        f"{FASTAPI_BASE_URL}/vm/destroy",
        json={"vm_name": vm_name},
        timeout=20,
    )
    res.raise_for_status()
    return res.json()
