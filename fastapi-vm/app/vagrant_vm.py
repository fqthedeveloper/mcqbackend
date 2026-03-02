import os
import re
import socket
import subprocess
from typing import Any, Dict
import uuid
import time
import shutil
import paramiko
import threading
import sys

from .config import (
    VAGRANT_BASE_BOX,
    VAGRANT_VM_ROOT,
    VM_USER,
    VM_PASSWORD,
    SSH_TIMEOUT,
    VM_IP_BASE,
    VM_IP_START,
    EXTRA_DISKS,
)

# ============================================================
# CROSS-PLATFORM FILE LOCKING (SAFE)
# ============================================================

if sys.platform == "win32":
    import msvcrt

    def lock_file(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

    def unlock_file(f):
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except:
            pass
else:
    import fcntl

    def lock_file(f):
        fcntl.flock(f, fcntl.LOCK_EX)

    def unlock_file(f):
        try:
            fcntl.flock(f, fcntl.LOCK_UN)
        except:
            pass

# ============================================================
# GLOBAL LIMITER
# ============================================================

MAX_PARALLEL_VM_START = 5
vm_boot_semaphore = threading.Semaphore(MAX_PARALLEL_VM_START)

IP_LOCK_FILE = os.path.join(VAGRANT_VM_ROOT, "ip_alloc.lock")

# ============================================================
# THREAD-SAFE IP ALLOCATION (FIXED — NO DUPLICATE IP)
# ============================================================

def allocate_ip(vm_dir):
    os.makedirs(VAGRANT_VM_ROOT, exist_ok=True)

    lockfile = open(IP_LOCK_FILE, "a+")
    lock_file(lockfile)

    try:
        used_ips = set()

        for d in os.listdir(VAGRANT_VM_ROOT):
            ip_file = os.path.join(VAGRANT_VM_ROOT, d, "ip.txt")
            if os.path.exists(ip_file):
                with open(ip_file) as f:
                    used_ips.add(f.read().strip())

        for i in range(VM_IP_START, 250):
            candidate = f"{VM_IP_BASE}{i}"
            if candidate not in used_ips:
                # RESERVE IP IMMEDIATELY
                os.makedirs(vm_dir, exist_ok=True)
                with open(os.path.join(vm_dir, "ip.txt"), "w") as f:
                    f.write(candidate)
                return candidate

        raise Exception("No free IPs available")

    finally:
        unlock_file(lockfile)
        lockfile.close()

# ============================================================
# VAGRANTFILE CREATION
# ============================================================

def create_vagrantfile(vm_dir, vm_name, vm_ip):

    content = f"""
Vagrant.configure("2") do |config|
  config.vm.box = "{VAGRANT_BASE_BOX}"
  config.vm.hostname = "{vm_name}"

  config.vm.synced_folder ".", "/vagrant", disabled: true
  config.vm.network "private_network", ip: "{vm_ip}"

  config.ssh.insert_key = false
  config.ssh.username = "vagrant"
  config.ssh.password = "vagrant"

  config.vm.provider "virtualbox" do |vb|
    vb.name = "{vm_name}"
    vb.memory = 2048
    vb.cpus = 2
    vb.customize ["modifyvm", :id, "--firmware", "efi"]
  end
end
"""

    with open(os.path.join(vm_dir, "Vagrantfile"), "w", encoding="utf-8") as f:
        f.write(content.strip())

# ============================================================
# ATTACH EXTRA DISKS
# ============================================================

def attach_extra_disks(vm_name, vm_dir):

    try:
        subprocess.run(
            ["VBoxManage", "controlvm", vm_name, "poweroff"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(2)
    except:
        pass

    subprocess.run([
        "VBoxManage", "storagectl", vm_name,
        "--name", "ExamSATA",
        "--add", "sata",
        "--controller", "IntelAhci"
    ], check=False)

    for index, disk in enumerate(EXTRA_DISKS):
        disk_path = os.path.join(vm_dir, disk["name"]).replace("\\", "/")
        size = disk["size_mb"]

        subprocess.run([
            "VBoxManage", "createmedium", "disk",
            "--filename", disk_path,
            "--size", str(size)
        ], check=False)

        subprocess.run([
            "VBoxManage", "storageattach", vm_name,
            "--storagectl", "ExamSATA",
            "--port", str(index),
            "--device", "0",
            "--type", "hdd",
            "--medium", disk_path
        ], check=False)

# ============================================================
# WAIT FOR SSH (HARDENED)
# ============================================================

def wait_for_ssh(ip):
    print(f"Waiting for SSH on {ip}...")

    start_time = time.time()
    last_error = None

    while time.time() - start_time < SSH_TIMEOUT:

        try:
            sock = socket.create_connection((ip, 22), timeout=5)
            sock.close()
        except Exception:
            time.sleep(5)
            continue

        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                ip,
                username="vagrant",
                password="vagrant",
                timeout=20,
                allow_agent=False,
                look_for_keys=False
            )
            ssh.close()
            print("SSH ready")
            return
        except Exception as e:
            last_error = e
            time.sleep(5)

    raise Exception(f"SSH timeout for {ip}: {last_error}")

# ============================================================
# PREPARE EXAM USER
# ============================================================

def prepare_exam_user(ip):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, username="vagrant", password="vagrant")

    commands = f"""
sudo useradd -m -s /bin/bash {VM_USER} || true
echo "{VM_USER}:{VM_PASSWORD}" | sudo chpasswd
sudo usermod -aG wheel {VM_USER} || true
sudo mkdir -p /etc/sudoers.d
echo "{VM_USER} ALL=(ALL) ALL" | sudo tee /etc/sudoers.d/{VM_USER}
sudo chmod 440 /etc/sudoers.d/{VM_USER}

# Enable SSH password login
sudo sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config
sudo sed -i 's/^PermitRootLogin no/PermitRootLogin yes/' /etc/ssh/sshd_config


sudo systemctl restart sshd
"""

    ssh.exec_command(commands)
    ssh.close()

# ============================================================
# RUN INIT SCRIPT (SAFE)
# ============================================================

def run_init_script(ip, init_script):

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh.connect(
        ip,
        username="vagrant",
        password="vagrant",
        allow_agent=False,
        look_for_keys=False,
        timeout=30
    )

    remote_path = "/tmp/init_exam.sh"

    full_script = f"""#!/bin/bash
set -e
set -x

echo "========== INIT START =========="

{init_script}

echo "========== INIT END =========="
"""

    # Upload script
    sftp = ssh.open_sftp()
    with sftp.file(remote_path, "w") as f:
        f.write(full_script)
    sftp.close()

    ssh.exec_command(f"chmod +x {remote_path}")

    # Execute and WAIT properly
    stdin, stdout, stderr = ssh.exec_command(
        f"echo vagrant | sudo -S bash {remote_path}",
        get_pty=True
    )

    exit_status = stdout.channel.recv_exit_status()

    output = stdout.read().decode(errors="ignore")
    error = stderr.read().decode(errors="ignore")

    print("===== INIT SCRIPT OUTPUT =====")
    print(output)
    print(error)
    print("===== END INIT OUTPUT =====")

    ssh.close()

    if exit_status != 0:
        raise Exception(
            f"Init script failed with exit code {exit_status}\n{output}\n{error}"
        )

# ============================================================
# START VM (NO CRASH, SAFE CONCURRENCY)
# ============================================================

def start_vm(init_script=None):
    with vm_boot_semaphore:

        vm_id = f"exam-{uuid.uuid4().hex[:6]}"
        vm_dir = os.path.join(VAGRANT_VM_ROOT, vm_id)

        vm_ip = allocate_ip(vm_dir)

        create_vagrantfile(vm_dir, vm_id, vm_ip)

        try:
            # FIRST BOOT
            subprocess.run(["vagrant", "up"], cwd=vm_dir, check=True)

            wait_for_ssh(vm_ip)

            # Prepare exam user
            prepare_exam_user(vm_ip)

            # Stop VM before disk attach
            subprocess.run(["vagrant", "halt"], cwd=vm_dir, check=True)

            if EXTRA_DISKS:
                attach_extra_disks(vm_id, vm_dir)

            # SECOND BOOT
            subprocess.run(["vagrant", "up"], cwd=vm_dir, check=True)

            wait_for_ssh(vm_ip)

            time.sleep(5)

            return {
                "vm_name": vm_id,
                "vm_ip": vm_ip,
                "username": VM_USER,
                "password": VM_PASSWORD,
            }

        except Exception as e:
            try:
                subprocess.run(["vagrant", "destroy", "-f"], cwd=vm_dir)
            except:
                pass

            shutil.rmtree(vm_dir, ignore_errors=True)
            raise e

# ============================================================
# VERIFY VM
# ============================================================

def verify_vm(vm_ip: str, verify_script: str) -> Dict[str, Any]:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(vm_ip, username="vagrant", password="vagrant")

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

    ssh.close()

    full_output = output + "\n" + error
    match = re.search(r"FINAL_SCORE=(\d+)", full_output)
    score = int(match.group(1)) if match else 0

    return {
        "score": score,
        "raw_output": full_output
    }

# ============================================================
# COPY HISTORY
# ============================================================

# def copy_vm_history(vm_name: str):
#     vm_dir = os.path.join(VAGRANT_VM_ROOT, vm_name)
#     ip_file = os.path.join(vm_dir, "ip.txt")

#     if not os.path.exists(ip_file):
#         return None

#     vm_ip = open(ip_file).read().strip()

#     history_dir = os.path.join(BASE_DIR, vm_name)
#     os.makedirs(history_dir, exist_ok=True)

#     ssh = paramiko.SSHClient()
#     ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#     ssh.connect(vm_ip, username="vagrant", password="vagrant")

#     try:
#         ssh.exec_command("history -a")

#         stdin, stdout, stderr = ssh.exec_command(
#             "echo vagrant | sudo -S bash -c 'history -a && cat /root/.bash_history 2>/dev/null'"
#         )
#         root_history = stdout.read().decode(errors="ignore")

#         with open(os.path.join(history_dir, "root_history.txt"), "w") as f:
#             f.write(root_history)

#         stdin, stdout, stderr = ssh.exec_command(
#             "cat /home/vagrant/.bash_history 2>/dev/null"
#         )
#         user_history = stdout.read().decode(errors="ignore")

#         with open(os.path.join(history_dir, "exam_user_history.txt"), "w") as f:
#             f.write(user_history)

#     finally:
#         ssh.close()

#     return history_dir

# ============================================================
# DESTROY VM
# ============================================================

def destroy_vm_local(vm_name: str):
    vm_dir = os.path.join(VAGRANT_VM_ROOT, vm_name)

    if not os.path.isdir(vm_dir):
        print(f"[DESTROY] VM folder not found: {vm_dir}")
        return False

    try:
        print(f"[DESTROY] Running vagrant destroy in {vm_dir}")

        result = subprocess.run(
            ["vagrant", "destroy", "-f"],
            cwd=vm_dir,
            capture_output=True,
            text=True,
            check=True
        )

        print("[DESTROY OUTPUT]")
        print(result.stdout)
        print(result.stderr)

        shutil.rmtree(vm_dir, ignore_errors=True)

        print(f"[DESTROY] Folder removed: {vm_dir}")

        return True

    except subprocess.CalledProcessError as e:
        print("[DESTROY ERROR]")
        print(e.stdout)
        print(e.stderr)
        return False