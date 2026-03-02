import sys
import threading
import uuid
import re
from typing import Dict, Any

from fastapi import FastAPI
from pydantic import BaseModel
import paramiko

from .vagrant_vm import (
    start_vm as start_vm_internal,
    run_init_script,      # <-- IMPORTANT
    destroy_vm_local,
)

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

app = FastAPI(title="Exam VM Service")

vm_status_store: Dict[str, Dict[str, Any]] = {}
vm_status_lock = threading.Lock()


class StartVMRequest(BaseModel):
    init_script: str


class VerifyVMRequest(BaseModel):
    vm_ip: str
    script: str


class DestroyVMRequest(BaseModel):
    vm_name: str


# ============================================================
# BACKGROUND WORKER
# ============================================================

def background_vm_worker(vm_name: str, init_script: str):

    try:
        with vm_status_lock:
            vm_status_store[vm_name] = {"status": "starting"}

        # ---- BOOT VM ONLY
        result = start_vm_internal(init_script=None)

        vm_ip = result.get("vm_ip")

        if not vm_ip:
            raise Exception("VM IP missing after boot")

        with vm_status_lock:
            vm_status_store[vm_name] = {
                "status": "booted",
                "vm_ip": vm_ip
            }

        # ---- RUN INIT SCRIPT PROPERLY
        if init_script and init_script.strip():
            try:
                run_init_script(vm_ip, init_script)
            except Exception as e:
                with vm_status_lock:
                    vm_status_store[vm_name] = {
                        "status": "failed",
                        "error": f"Init script failed: {str(e)}"
                    }
                return

        # ---- SUCCESS
        with vm_status_lock:
            vm_status_store[vm_name] = {
                "status": "running",
                "vm_ip": vm_ip,
                "username": result.get("username"),
                "password": result.get("password"),
            }

    except Exception as e:
        with vm_status_lock:
            vm_status_store[vm_name] = {
                "status": "failed",
                "error": str(e)
            }


# ============================================================
# START ENDPOINT (NON BLOCKING)
# ============================================================

@app.post("/vm/start")
def api_start_vm(data: StartVMRequest):

    vm_name = f"exam-{uuid.uuid4().hex[:6]}"

    thread = threading.Thread(
        target=background_vm_worker,
        args=(vm_name, data.init_script),
        daemon=True
    )
    thread.start()

    return {
        "status": "starting",
        "vm_name": vm_name
    }


# ============================================================
# STATUS
# ============================================================

@app.get("/vm/status/{vm_name}")
def api_vm_status(vm_name: str):

    with vm_status_lock:
        status = vm_status_store.get(vm_name)

    if not status:
        return {"status": "unknown"}

    return status


# ============================================================
# VERIFY
# ============================================================

@app.post("/vm/verify")
def api_verify_vm(data: VerifyVMRequest):

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            hostname=data.vm_ip,
            username="vagrant",
            password="vagrant",
            timeout=20
        )

        remote_path = "/tmp/verify_exam.sh"

        full_script = f"""#!/bin/bash
SCORE=0
set +e

{data.script}

echo "FINAL_SCORE=$SCORE"
"""

        sftp = ssh.open_sftp()
        with sftp.file(remote_path, "w") as f:
            f.write(full_script)
        sftp.close()

        ssh.exec_command(f"chmod +x {remote_path}")

        stdin, stdout, stderr = ssh.exec_command(
            f"echo vagrant | sudo -S bash {remote_path}"
        )

        output = stdout.read().decode(errors="ignore")
        error = stderr.read().decode(errors="ignore")

        full_output = output + "\n" + error

        match = re.search(r"FINAL_SCORE=(\d+)", full_output)
        score = int(match.group(1)) if match else 0

        return {
            "score": score,
            "raw_output": full_output
        }

    except Exception as e:
        return {
            "score": 0,
            "raw_output": str(e)
        }

    finally:
        ssh.close()


# ============================================================
# DESTROY
# ============================================================

@app.post("/vm/destroy")
def api_destroy_vm(data: DestroyVMRequest):

    destroyed = destroy_vm_local(data.vm_name)

    with vm_status_lock:
        if data.vm_name in vm_status_store:
            del vm_status_store[data.vm_name]

    return {
        "status": "destroyed" if destroyed else "failed"
    }