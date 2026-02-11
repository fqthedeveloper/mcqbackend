import os
import subprocess
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
)

# =============================
# IP ALLOCATION
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
# VAGRANTFILE
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
    with open(os.path.join(vm_dir, "Vagrantfile"), "w") as f:
        f.write(content.strip())

# =============================
# WAIT FOR SSH
# =============================
def wait_for_ssh(ip):
    for _ in range(60):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ip, username="vagrant", password="vagrant", timeout=5)
            ssh.close()
            return
        except Exception:
            time.sleep(5)
    raise Exception("SSH not ready")

# =============================
# USER PREP
# =============================
def prepare_exam_user(ip):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, username="vagrant", password="vagrant")

    ssh.exec_command(
        f"""
sudo useradd -m -s /bin/bash {VM_USER} || true
echo "{VM_USER}:{VM_PASSWORD}" | sudo chpasswd
sudo usermod -aG wheel {VM_USER}
echo "{VM_USER} ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/{VM_USER}
sudo chmod 440 /etc/sudoers.d/{VM_USER}
"""
    )
    ssh.close()

# =============================
# INIT SCRIPT (FINAL & SAFE)
# =============================
def run_init_script(ip, init_script):
    if not init_script.strip():
        return

    # 🔥 Normalize Windows CRLF → LF
    init_script = init_script.replace("\r\n", "\n").strip() + "\n"

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, username="vagrant", password="vagrant")

    sftp = ssh.open_sftp()
    remote = "/tmp/init_exam.sh"

    full_script = f"""#!/bin/bash
set -euxo pipefail

echo "=== INIT SCRIPT START ==="

{init_script}

echo "=== INIT SCRIPT END ==="
"""

    with sftp.file(remote, "w") as f:
        f.write(full_script)

    sftp.close()

    # HARDEN FILE
    ssh.exec_command(f"sudo chmod 755 {remote}")
    ssh.exec_command(f"sudo sed -i 's/\\r$//' {remote}")

    # 🔥 CRITICAL FIX:
    # - use sh -c
    # - redirect INSIDE sudo
    # - no Paramiko race
    cmd = (
        "sudo -S sh -c "
        f"'/bin/bash {remote} > /root/init_exam.log 2>&1'"
    )

    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
    stdin.write("vagrant\n")
    stdin.flush()

    exit_code = stdout.channel.recv_exit_status()

    if exit_code != 0:
        log = ssh.exec_command(
            "sudo cat /root/init_exam.log || echo 'NO LOG FILE'"
        )[1].read().decode()
        ssh.close()
        raise Exception(f"Init script failed. Log:\n{log}")

    ssh.close()

# =============================
# START VM
# =============================
def start_vm(init_script):
    vm_id = f"exam-{uuid.uuid4().hex[:6]}"
    vm_dir = os.path.join(VAGRANT_VM_ROOT, vm_id)
    vm_ip = allocate_ip()

    os.makedirs(vm_dir, exist_ok=True)
    create_vagrantfile(vm_dir, vm_id, vm_ip)

    subprocess.run(["vagrant", "up"], cwd=vm_dir, check=True)

    with open(os.path.join(vm_dir, "ip.txt"), "w") as f:
        f.write(vm_ip)

    wait_for_ssh(vm_ip)
    prepare_exam_user(vm_ip)
    run_init_script(vm_ip, init_script)

    return {
        "vm_name": vm_id,
        "vm_ip": vm_ip,
        "username": VM_USER,
        "password": VM_PASSWORD,
    }

# =============================
# VERIFY
# =============================
def verify_vm(vm_ip, verify_script):
    verify_script = verify_script.replace("\r\n", "\n")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(vm_ip, username=VM_USER, password=VM_PASSWORD)

    stdin, stdout, stderr = ssh.exec_command(
        f"sudo /bin/bash -c '{verify_script}'"
    )

    out = stdout.read().decode()
    ssh.close()

    return out

# =============================
# COPY VM HISTORY
# =============================
def copy_vm_history(vm_name):
    """
    Copies student VM files before destroy.
    Stored in:
    vms_history/<vm_name>/
    """

    vm_dir = os.path.join(VAGRANT_VM_ROOT, vm_name)
    ip_file = os.path.join(vm_dir, "ip.txt")

    if not os.path.exists(ip_file):
        return None

    vm_ip = open(ip_file).read().strip()

    history_root = os.path.join(BASE_DIR, "vms_history")
    os.makedirs(history_root, exist_ok=True)

    save_dir = os.path.join(history_root, vm_name)
    os.makedirs(save_dir, exist_ok=True)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(vm_ip, username=VM_USER, password=VM_PASSWORD)

    sftp = ssh.open_sftp()

    # copy root history
    try:
        sftp.get("/root/.bash_history",
                 os.path.join(save_dir, "root_bash_history.txt"))
    except:
        pass

    # copy kiosk user history
    try:
        sftp.get(f"/home/{VM_USER}/.bash_history",
                 os.path.join(save_dir, "user_bash_history.txt"))
    except:
        pass

    # copy home directory
    try:
        download_directory(sftp, f"/home/{VM_USER}", 
                           os.path.join(save_dir, "home"))
    except:
        pass

    sftp.close()
    ssh.close()

    return save_dir


def download_directory(sftp, remote_dir, local_dir):
    import stat

    os.makedirs(local_dir, exist_ok=True)

    for item in sftp.listdir_attr(remote_dir):
        remote_path = f"{remote_dir}/{item.filename}"
        local_path = os.path.join(local_dir, item.filename)

        if stat.S_ISDIR(item.st_mode):
            download_directory(sftp, remote_path, local_path)
        else:
            try:
                sftp.get(remote_path, local_path)
            except:
                pass

# =============================
# DESTROY
# =============================
def destroy_vm(vm_name):
    vm_dir = os.path.join(VAGRANT_VM_ROOT, vm_name)
    if os.path.exists(vm_dir):
        subprocess.run(["vagrant", "destroy", "-f"], cwd=vm_dir)
        shutil.rmtree(vm_dir, ignore_errors=True)
