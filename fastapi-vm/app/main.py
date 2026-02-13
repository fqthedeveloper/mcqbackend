import sys
from fastapi import FastAPI
from pydantic import BaseModel

from .vagrant_vm import (
    start_vm,
    verify_vm,
    destroy_vm,
    copy_vm_history
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


@app.post("/vm/verify")
def api_verify_vm(data: VerifyVMRequest):
    result = verify_vm(data.vm_ip, data.script)
    return result


@app.post("/vm/destroy")
def api_destroy_vm(data: DestroyVMRequest):

    history_path = copy_vm_history(data.vm_name)
    destroy_vm(data.vm_name)

    return {
        "status": "destroyed",
        "history_path": history_path
    }