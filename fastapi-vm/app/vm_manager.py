import platform
import subprocess
import time
import uuid


def start_vm(snapshot: str, username: str):
    os_name = platform.system()
    vm_name = f"vm-{username}-{uuid.uuid4().hex[:6]}"

    if os_name == "Windows":
        subprocess.run(
            ["VBoxManage", "clonevm", snapshot, "--name", vm_name, "--register"],
            check=True
        )
        subprocess.run(
            ["VBoxManage", "startvm", vm_name, "--type", "headless"],
            check=True
        )

    else:  # Linux / Kali / Ubuntu
        subprocess.run(
            ["vboxmanage", "clonevm", snapshot, "--name", vm_name, "--register"],
            check=True
        )
        subprocess.run(
            ["vboxmanage", "startvm", vm_name, "--type", "headless"],
            check=True
        )

    time.sleep(15)

    ip_cmd = (
        ["VBoxManage"] if os_name == "Windows" else ["vboxmanage"]
    ) + [
        "guestproperty", "get",
        vm_name, "/VirtualBox/GuestInfo/Net/0/V4/IP"
    ]

    result = subprocess.check_output(ip_cmd).decode()
    vm_ip = result.split()[-1]

    return {
        "vm_name": vm_name,
        "vm_ip": vm_ip
    }


def destroy_vm(vm_name: str):
    os_name = platform.system()
    cmd = ["VBoxManage"] if os_name == "Windows" else ["vboxmanage"]

    subprocess.run(cmd + ["controlvm", vm_name, "poweroff"],
                   stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)

    subprocess.run(cmd + ["unregistervm", vm_name, "--delete"],
                   stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)

    return {"status": "destroyed"}
