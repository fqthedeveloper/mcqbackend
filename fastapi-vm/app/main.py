import sys
from fastapi import FastAPI
from pydantic import BaseModel
import paramiko
import os
import re
from typing import Dict, Any

from .vagrant_vm import (
    start_vm,
    verify_vm,
    destroy_vm_local,
)

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

app = FastAPI(title="Exam VM Service")


class StartVMRequest(BaseModel):
    init_script: str


class VerifyVMRequest(BaseModel):
    vm_ip: str
    script: str


class DestroyVMRequest(BaseModel):
    vm_name: str


@app.post("/vm/start")
def api_start_vm(data: StartVMRequest):
    return start_vm(data.init_script)


def execute_verify(vm_ip: str, verify_script: str) -> Dict[str, Any]:

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            hostname=vm_ip,
            username="vagrant",
            password="vagrant",
            timeout=20
        )

        remote_path = "/tmp/verify_exam.sh"

        full_script = f"""#!/bin/bash
SCORE=0
set +e

{verify_script}

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

        print("========== VERIFY OUTPUT ==========")
        print(full_output)
        print("===================================")

        match = re.search(r"FINAL_SCORE=(\d+)", full_output)

        score = int(match.group(1)) if match else 0

        return {
            "score": score,
            "raw_output": full_output
        }

    except Exception as e:
        return {
            "score": 0,
            "raw_output": f"Verification error: {str(e)}"
        }

    finally:
        ssh.close()


@app.post("/vm/verify")
def api_verify_vm(data: VerifyVMRequest):
    return execute_verify(data.vm_ip, data.script)


@app.post("/vm/destroy")
def api_destroy_vm(data: DestroyVMRequest):

    destroyed = destroy_vm_local(data.vm_name)

    return {
        "status": "destroyed" if destroyed else "failed",
    }