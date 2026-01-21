import paramiko
from .config import VM_USER, VM_PASSWORD, SSH_TIMEOUT


def verify_vm(vm_ip: str, command: str, expected: str):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            vm_ip,
            username=VM_USER,
            password=VM_PASSWORD,
            timeout=SSH_TIMEOUT
        )

        stdin, stdout, stderr = client.exec_command(command)
        output = stdout.read().decode().strip()

        return {
            "success": expected in output,
            "output": output
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

    finally:
        client.close()
