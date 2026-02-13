import os
import re
import socket
import subprocess
from typing import Any, Dict
import uuid
import time
import shutil
import paramiko

from .config import (
    BASE_DIR,
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
# IP ALLOCATION
# ============================================================
def allocate_ip():
    os.makedirs(VAGRANT_VM_ROOT, exist_ok=True)
    used_ips = set()

    for d in os.listdir(VAGRANT_VM_ROOT):
        ip_file = os.path.join(VAGRANT_VM_ROOT, d, "ip.txt")
        if os.path.exists(ip_file):
            with open(ip_file) as f:
                used_ips.add(f.read().strip())

    for i in range(VM_IP_START, 250):
        candidate = f"{VM_IP_BASE}{i}"
        if candidate not in used_ips:
            return candidate

    raise Exception("No free IPs available")


# ============================================================
# CREATE VAGRANTFILE
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

    subprocess.run(["VBoxManage", "controlvm", vm_name, "poweroff"], check=True)
    time.sleep(2)

    subprocess.run([
        "VBoxManage", "storagectl", vm_name,
        "--name", "ExamSATA",
        "--add", "sata",
        "--controller", "IntelAhci"
    ], check=True)

    for index, disk in enumerate(EXTRA_DISKS):
        disk_path = os.path.join(vm_dir, disk["name"]).replace("\\", "/")
        size = disk["size_mb"]

        subprocess.run([
            "VBoxManage", "createmedium", "disk",
            "--filename", disk_path,
            "--size", str(size)
        ], check=True)

        subprocess.run([
            "VBoxManage", "storageattach", vm_name,
            "--storagectl", "ExamSATA",
            "--port", str(index),
            "--device", "0",
            "--type", "hdd",
            "--medium", disk_path
        ], check=True)

    subprocess.run(["VBoxManage", "startvm", vm_name, "--type", "headless"], check=True)


# ============================================================
# WAIT FOR SSH
# ============================================================
def wait_for_ssh(ip):

    print(f"Waiting for SSH on {ip}...")

    start_time = time.time()

    while time.time() - start_time < SSH_TIMEOUT:
        try:
            # Step 1: Check if port 22 is open
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((ip, 22))
            sock.close()

            if result != 0:
                print("Port 22 not open yet...")
                time.sleep(5)
                continue

            # Step 2: Try SSH login
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            ssh.connect(
                ip,
                username="vagrant",
                password="vagrant",
                timeout=5,
                allow_agent=False,
                look_for_keys=False
            )

            ssh.close()
            print("SSH is ready.")
            return

        except Exception as e:
            print(f"SSH not ready yet: {e}")
            time.sleep(5)

    raise Exception(f"SSH did not become ready in time for IP {ip}")


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
sudo sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config
sudo systemctl restart sshd
"""

    ssh.exec_command(commands)
    ssh.close()


# ============================================================
# RUN INIT SCRIPT
# ============================================================
def run_init_script(ip, init_script):

    if not init_script.strip():
        return

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, username="vagrant", password="vagrant")

    sftp = ssh.open_sftp()
    remote_path = "/tmp/init_exam.sh"

    full_script = f"""#!/bin/bash
set -euxo pipefail

echo "=== INIT START ==="
{init_script}
echo "=== INIT END ==="
"""

    with sftp.file(remote_path, "w") as f:
        f.write(full_script)

    sftp.close()

    ssh.exec_command(f"sudo chmod 755 {remote_path}")

    stdin, stdout, stderr = ssh.exec_command(
        f"sudo /bin/bash {remote_path}",
        get_pty=True
    )
    stdin.write("vagrant\n")
    stdin.flush()

    exit_code = stdout.channel.recv_exit_status()

    if exit_code != 0:
        log = stdout.read().decode()
        ssh.close()
        raise Exception(f"Init script failed:\n{log}")

    ssh.close()


# ============================================================
# START VM
# ============================================================
def start_vm(init_script):

    vm_id = f"exam-{uuid.uuid4().hex[:6]}"
    vm_dir = os.path.join(VAGRANT_VM_ROOT, vm_id)
    vm_ip = allocate_ip()

    os.makedirs(vm_dir, exist_ok=True)

    create_vagrantfile(vm_dir, vm_id, vm_ip)

    # Boot VM
    subprocess.run(["vagrant", "up"], cwd=vm_dir, check=True)

    # Wait for system to stabilize before disk operations
    print("Initial boot delay...")
    time.sleep(20)

    # Attach disks (this will reboot VM)
    attach_extra_disks(vm_id, vm_dir)

    # Wait again after reboot
    print("Waiting after reboot...")
    time.sleep(25)

    with open(os.path.join(vm_dir, "ip.txt"), "w") as f:
        f.write(vm_ip)

    # Now wait for SSH properly
    wait_for_ssh(vm_ip)

    # Prepare exam user
    prepare_exam_user(vm_ip)

    # Run init script
    run_init_script(vm_ip, init_script)

    return {
        "vm_name": vm_id,
        "vm_ip": vm_ip,
        "username": VM_USER,
        "password": VM_PASSWORD,
    }


# ============================
# VERIFY VM (REAL EXECUTION)
# ============================

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

    if match:
        score = int(match.group(1))
    else:
        score = 0

    return {
        "score": score,
        "raw_output": full_output
    }


# ============================
# COPY HISTORY
# ============================

def copy_vm_history(vm_name: str):

    vm_dir = os.path.join(VAGRANT_VM_ROOT, vm_name)
    ip_file = os.path.join(vm_dir, "ip.txt")

    if not os.path.exists(ip_file):
        return None

    vm_ip = open(ip_file).read().strip()

    history_dir = os.path.join(BASE_DIR, vm_name)
    os.makedirs(history_dir, exist_ok=True)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(vm_ip, username="vagrant", password="vagrant")

    try:
        ssh.exec_command("history -a")

        stdin, stdout, stderr = ssh.exec_command(
            "echo vagrant | sudo -S bash -c 'history -a && cat /root/.bash_history 2>/dev/null'"
        )
        root_history = stdout.read().decode(errors="ignore")

        with open(os.path.join(history_dir, "root_history.txt"), "w") as f:
            f.write(root_history)

        stdin, stdout, stderr = ssh.exec_command(
            "cat /home/vagrant/.bash_history 2>/dev/null"
        )
        user_history = stdout.read().decode(errors="ignore")

        with open(os.path.join(history_dir, "exam_user_history.txt"), "w") as f:
            f.write(user_history)

    finally:
        ssh.close()

    return history_dir


# ============================
# DESTROY VM
# ============================

def destroy_vm(vm_name: str):

    vm_dir = os.path.join(VAGRANT_VM_ROOT, vm_name)

    if os.path.exists(vm_dir):
        subprocess.run(["vagrant", "destroy", "-f"], cwd=vm_dir)
        shutil.rmtree(vm_dir, ignore_errors=True)

    return True