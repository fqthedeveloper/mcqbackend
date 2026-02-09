from pydantic import BaseModel


class StartVMRequest(BaseModel):
    snapshot: str
    username: str
    init_script: str



class VerifyVMRequest(BaseModel):
    vm_ip: str
    command: str
    expected: str


class DestroyVMRequest(BaseModel):
    vm_name: str
