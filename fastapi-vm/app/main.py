from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import uuid
import re

app = FastAPI(title="VM Service")

USE_MOCK_VM = True  # 🔥 TRUE = no VirtualBox, FALSE = real VM

BASE_VM_NAME = "Redhat_BaseImage"


class StartVMRequest(BaseModel):
    snapshot: str
    username: str


class VerifyVMRequest(BaseModel):
    vm_ip: str
    command: str
    expected: str


class DestroyVMRequest(BaseModel):
    vm_name: str


def sanitize(text: str):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", text)


@app.post("/vm/start")
def start_vm(data: StartVMRequest):

    if USE_MOCK_VM:
        return {
            "vm_name": f"vm-{uuid.uuid4().hex[:6]}",
            "vm_ip": "192.168.56.100"
        }

    safe_user = sanitize(data.username)
    vm_name = f"vm-{safe_user}-{uuid.uuid4().hex[:6]}"

    try:
        # 🔥 CLONE FROM BASE VM + SNAPSHOT
        subprocess.run(
            [
                "VBoxManage",
                "clonevm",
                BASE_VM_NAME,
                "--snapshot",
                data.snapshot,
                "--name",
                vm_name,
                "--register"
            ],
            check=True,
            capture_output=True,
            text=True
        )

        subprocess.run(
            ["VBoxManage", "startvm", vm_name, "--type", "headless"],
            check=True,
            capture_output=True,
            text=True
        )

        return {
            "vm_name": vm_name,
            "vm_ip": "192.168.56.101"
        }

    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=e.stderr or "VirtualBox error"
        )



@app.post("/vm/verify")
def verify_vm(data: VerifyVMRequest):
    return {"success": True}


@app.post("/vm/destroy")
def destroy_vm(data: DestroyVMRequest):
    try:
        subprocess.run(
            ["VBoxManage", "controlvm", data.vm_name, "poweroff"],
            capture_output=True
        )
        subprocess.run(
            ["VBoxManage", "unregistervm", data.vm_name, "--delete"],
            capture_output=True
        )
        return {"status": "destroyed"}
    except Exception:
        return {"status": "failed"}
