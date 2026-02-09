import os
import subprocess
import uuid
import time
import shutil
import paramiko

from .config import (
    VAGRANT_BASE_BOX,
    VAGRANT_VM_ROOT,
    VM_USER,
    VM_PASSWORD,
    SSH_TIMEOUT,
    VM_IP_BASE,
    VM_IP_START,
)

# =============================
# ALLOCATE STATIC IP
# =============================
def allocate_ip():
    os.makedirs(VAGRANT_VM_ROOT, exist_ok=True)
    used = set()

    for d in os.listdir(VAGRANT_VM_ROOT):
        ipf = os.path.join(VAGRANT_VM_ROOT, d, "ip.txt")
        if os.path.exists(ipf):
            used.add(open(ipf).read().strip())

    for i in range(VM_IP_START, 250):
        ip = f"{VM_IP_BASE}{i}"
        if ip not in used:
            return ip

    raise Exception("No free IPs available")

# =============================
# CREATE VAGRANTFILE
# =============================
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
        f.write(content.strip() + "\n")

# =============================
# WAIT FOR SSH
# =============================
def wait_for_ssh(ip):
    for _ in range(60):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                ip,
                username="vagrant",
                password="vagrant",
                timeout=5
            )
            ssh.close()
            return
        except Exception:
            time.sleep(5)
    raise Exception("SSH not ready")

# =============================
# CREATE KIOSK USER (ROOT VIA SUDO)
# =============================
def prepare_exam_user(ip):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        ip,
        username="vagrant",
        password="vagrant",
        timeout=SSH_TIMEOUT
    )

    commands = f"""
sudo useradd -m {VM_USER} || true
echo "{VM_USER}:{VM_PASSWORD}" | sudo chpasswd
sudo usermod -aG wheel {VM_USER}
echo "{VM_USER} ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/{VM_USER}

sudo sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config
sudo sed -i 's/^#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
sudo systemctl restart sshd
"""

    ssh.exec_command(commands)
    ssh.close()

# =============================
# START VM
# =============================
def start_vm(init_script: str):
    vm_id = f"exam-{uuid.uuid4().hex[:6]}"
    vm_dir = os.path.join(VAGRANT_VM_ROOT, vm_id)
    vm_ip = allocate_ip()

    os.makedirs(vm_dir, exist_ok=True)
    create_vagrantfile(vm_dir, vm_id, vm_ip)

    subprocess.run(
        ["vagrant", "up"],
        cwd=vm_dir,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    with open(os.path.join(vm_dir, "ip.txt"), "w") as f:
        f.write(vm_ip)

    wait_for_ssh(vm_ip)
    prepare_exam_user(vm_ip)

    return {
        "vm_name": vm_id,
        "vm_ip": vm_ip,
        "username": VM_USER,
        "password": VM_PASSWORD
    }

# =============================
# VERIFY
# =============================
def verify_vm(vm_ip, script):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(vm_ip, username=VM_USER, password=VM_PASSWORD)

    stdin, stdout, stderr = ssh.exec_command(f"sudo bash -c '{script}'")
    out = stdout.read().decode("utf-8", errors="replace")
    ssh.close()
    return out

# =============================
# DESTROY
# =============================
def destroy_vm(vm_name):
    vm_dir = os.path.join(VAGRANT_VM_ROOT, vm_name)
    if os.path.exists(vm_dir):
        subprocess.run(["vagrant", "destroy", "-f"], cwd=vm_dir)
        shutil.rmtree(vm_dir, ignore_errors=True)
    return {"status": "destroyed"}
