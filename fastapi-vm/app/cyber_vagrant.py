import os
import re
import sys
import json
import time
import uuid
import shutil
import random
import socket
import string
import threading
import subprocess

from pathlib import Path

import paramiko



# =========================================================
# ROOT
# =========================================================

LABS_ROOT = Path("cyberlabs")

LABS_ROOT.mkdir(
    exist_ok=True
)

IP_LOCK_FILE = (
    LABS_ROOT /
    "ip_alloc.lock"
)

VM_IP_BASE = "192.168.56."

VM_IP_START = 10

SSH_TIMEOUT = 1200


# =========================================================
# LOCKS
# =========================================================

BOX_LOCKS = {}

BOX_LOCKS_MUTEX = threading.Lock()

VM_BOOT_LOCK = threading.Lock()


# =========================================================
# FILE LOCK
# =========================================================

if sys.platform == "win32":

    import msvcrt

    def lock_file(f):

        msvcrt.locking(
            f.fileno(),
            msvcrt.LK_LOCK,
            1
        )

    def unlock_file(f):

        try:

            msvcrt.locking(
                f.fileno(),
                msvcrt.LK_UNLCK,
                1
            )

        except:
            pass

else:

    import fcntl

    def lock_file(f):

        fcntl.flock(
            f,
            fcntl.LOCK_EX
        )

    def unlock_file(f):

        try:

            fcntl.flock(
                f,
                fcntl.LOCK_UN
            )

        except:
            pass


# =========================================================
# RUN COMMAND
# =========================================================

def run_cmd(
    cmd,
    cwd=None,
    timeout=None
):

    print(f"[RUNNING] {cmd}")

    process = subprocess.Popen(

        cmd,

        shell=True,

        cwd=cwd,

        stdout=subprocess.PIPE,

        stderr=subprocess.STDOUT,

        text=True,

        bufsize=1,

        universal_newlines=True
    )

    output_lines = []

    start_time = time.time()

    while True:

        line = process.stdout.readline()

        if line:

            print(line.strip())

            output_lines.append(line)

        if process.poll() is not None:

            break

        if timeout:

            elapsed = time.time() - start_time

            if elapsed > timeout:

                process.kill()

                raise Exception(
                    f"Command timeout after {timeout} seconds"
                )

    remaining = process.stdout.read()

    if remaining:

        print(remaining)

        output_lines.append(remaining)

    output = "".join(output_lines)

    return {

        "stdout": output,

        "stderr": "",

        "returncode": process.returncode,
    }


# =========================================================
# RANDOM HELPERS
# =========================================================

def random_string(length=12):

    chars = (
        string.ascii_letters +
        string.digits
    )

    return "".join(

        random.choice(chars)

        for _ in range(length)
    )


def random_password(length=14):

    chars = (
        string.ascii_letters +
        string.digits +
        "!@#$%^&*"
    )

    return "".join(

        random.choice(chars)

        for _ in range(length)
    )


def random_username():

    return (
        "admin_" +
        random_string(6).lower()
    )


def random_port():

    return random.randint(
        2000,
        9000
    )


# =========================================================
# TEMPLATE RENDER
# =========================================================

def render_template(
    text,
    variables
):

    if not text:
        return ""

    for key, value in variables.items():

        text = text.replace(

            "{{ " + key + " }}",

            str(value)
        )

        text = text.replace(

            "{{" + key + "}}",

            str(value)
        )

    return text


# =========================================================
# GENERATE VARIABLES
# =========================================================

def generate_variables(
    schema
):

    variables = {}

    for key, value in schema.items():

        if value == "random_ip":

            variables[key] = (
                f"{VM_IP_BASE}{random.randint(50,240)}"
            )

        elif value == "random_port":

            variables[key] = (
                random_port()
            )

        elif value == "random_username":

            variables[key] = (
                random_username()
            )

        elif value == "random_password":

            variables[key] = (
                random_password()
            )

        elif value == "random_string":

            variables[key] = (
                random_string(24)
            )

        else:

            variables[key] = value

    return variables


# =========================================================
# ENSURE BOX EXISTS
# =========================================================

def ensure_box_exists(
    box_name
):

    with BOX_LOCKS_MUTEX:

        if box_name not in BOX_LOCKS:

            BOX_LOCKS[box_name] = (
                threading.Lock()
            )

    lock = BOX_LOCKS[box_name]

    with lock:

        result = run_cmd(
            "vagrant box list"
        )

        if box_name in result["stdout"]:

            print(
                f"[BOX EXISTS] {box_name}"
            )

            return

        print(
            f"[DOWNLOADING BOX] {box_name}"
        )

        result = run_cmd(

            f'vagrant box add "{box_name}" --provider virtualbox',

            timeout=7200
        )

        if result["returncode"] != 0:

            raise Exception(

                f"Failed downloading box:\n"

                f"{result['stdout']}"
            )

        print(
            f"[BOX READY] {box_name}"
        )


# =========================================================
# ALLOCATE IP
# =========================================================

def allocate_ip(
    vm_dir
):

    os.makedirs(
        LABS_ROOT,
        exist_ok=True
    )

    lockfile = open(
        IP_LOCK_FILE,
        "a+"
    )

    lock_file(lockfile)

    try:

        used_ips = set()

        for d in os.listdir(
            LABS_ROOT
        ):

            ip_file = (
                LABS_ROOT /
                d /
                "ip.txt"
            )

            if os.path.exists(
                ip_file
            ):

                with open(ip_file) as f:

                    used_ips.add(
                        f.read().strip()
                    )

        for i in range(
            VM_IP_START,
            250
        ):

            candidate = (
                f"{VM_IP_BASE}{i}"
            )

            if candidate not in used_ips:

                os.makedirs(
                    vm_dir,
                    exist_ok=True
                )

                with open(

                    Path(vm_dir) /
                    "ip.txt",

                    "w"

                ) as f:

                    f.write(candidate)

                return candidate

        raise Exception(
            "No free IP available"
        )

    finally:

        unlock_file(lockfile)

        lockfile.close()


# =========================================================
# BUILD VAGRANTFILE
# =========================================================

def build_vagrantfile(machine):

    vm_name = machine["vm_name"]

    vm_ip = machine["ip"]

    base_box = machine["base_box"]

    memory = machine.get(
        "memory_mb",
        2048
    )

    cpus = machine.get(
        "cpu_count",
        2
    )

    block = f'''
Vagrant.configure("2") do |config|

  config.vm.box = "{base_box}"

  config.vm.hostname = "{vm_name}"

  config.vm.synced_folder ".", "/vagrant", disabled: true

  config.vm.network "private_network", ip: "{vm_ip}"

  config.vm.boot_timeout = 1800

  config.vm.graceful_halt_timeout = 300

  config.ssh.username = "vagrant"

  config.ssh.password = "vagrant"

  config.ssh.insert_key = false

  config.ssh.keep_alive = true

  config.ssh.max_tries = 200

  config.vm.provider "virtualbox" do |vb|

    vb.gui = false

    vb.name = "{vm_name}"

    vb.memory = "{memory}"

    vb.cpus = {cpus}

    vb.customize [
      "modifyvm",
      :id,
      "--audio-enabled",
      "off"
    ]

    vb.customize [
      "modifyvm",
      :id,
      "--clipboard-mode",
      "disabled"
    ]

    vb.customize [
      "modifyvm",
      :id,
      "--draganddrop",
      "disabled"
    ]

    vb.customize [
      "modifyvm",
      :id,
      "--nictype1",
      "virtio"
    ]

    vb.customize [
      "modifyvm",
      :id,
      "--graphicscontroller",
      "vmsvga"
    ]

  end

end
'''

    return block


# =========================================================
# CREATE VAGRANTFILE
# =========================================================

def create_vagrantfile(
    vm_dir,
    machine
):

    content = build_vagrantfile(
        machine
    )

    with open(

        Path(vm_dir) /
        "Vagrantfile",

        "w",

        encoding="utf-8"

    ) as f:

        f.write(content)


# =========================================================
# WAIT SSH
# =========================================================

def wait_for_ssh(ip):

    print(f"[WAIT SSH] {ip}")

    start = time.time()

    while time.time() - start < SSH_TIMEOUT:

        try:

            ssh = paramiko.SSHClient()

            ssh.set_missing_host_key_policy(
                paramiko.AutoAddPolicy()
            )

            ssh.connect(

                ip,

                username="vagrant",

                password="vagrant",

                timeout=15,

                allow_agent=False,

                look_for_keys=False
            )

            ssh.close()

            print("[SSH READY]")

            return True

        except Exception as e:

            print(f"[SSH WAITING] {str(e)}")

            time.sleep(10)

    raise Exception(
        f"SSH timeout: {ip}"
    )


# =========================================================
# RUN INIT SCRIPT
# =========================================================

def run_init_script(
    machine,
    init_script
):

    ip = machine["ip"]

    ssh = paramiko.SSHClient()

    ssh.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )

    ssh.connect(

        ip,

        username="vagrant",

        password="vagrant",

        allow_agent=False,

        look_for_keys=False,

        timeout=60
    )

    remote_path = "/tmp/init.sh"

    full_script = f"""#!/bin/bash

set -e
set -x

export DEBIAN_FRONTEND=noninteractive

{init_script}
"""

    command = f'''
echo vagrant | sudo -S bash {remote_path}
'''

    sftp = ssh.open_sftp()

    with sftp.file(
        remote_path,
        "w"
    ) as f:

        f.write(full_script)

    sftp.close()

    ssh.exec_command(
        f"chmod +x {remote_path}"
    )

    stdin, stdout, stderr = ssh.exec_command(

        command,

        get_pty=True
    )

    exit_status = (
        stdout.channel.recv_exit_status()
    )

    output = stdout.read().decode(
        errors="ignore"
    )

    error = stderr.read().decode(
        errors="ignore"
    )

    ssh.close()

    print(output)

    print(error)

    if exit_status != 0:

        raise Exception(

            f"Init script failed\n"

            f"{output}\n"

            f"{error}"
        )


# =========================================================
# START MACHINE
# =========================================================

def start_machine(

    machine,

    init_script=""
):

    with VM_BOOT_LOCK:

        vm_name = machine["vm_name"]

        vm_dir = (
            LABS_ROOT /
            vm_name
        )

        vm_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        vb_test = run_cmd(
            "VBoxManage --version"
        )

        if vb_test["returncode"] != 0:

            raise Exception(
                "VirtualBox not installed"
            )

        ensure_box_exists(
            machine["base_box"]
        )

        vm_ip = allocate_ip(
            vm_dir
        )

        machine["ip"] = vm_ip

        create_vagrantfile(

            vm_dir,

            machine
        )

        try:

            print(
                f"[START VM] {vm_name}"
            )

            result = run_cmd(

                "vagrant up --provider=virtualbox",

                cwd=vm_dir,

                timeout=3600
            )

            print(result["stdout"])

            if result["returncode"] != 0:

                raise Exception(
                    result["stdout"]
                )

            wait_for_ssh(vm_ip)

            if init_script:

                run_init_script(

                    machine,

                    init_script
                )

            return {

                "vm_name":
                    vm_name,

                "vm_ip":
                    vm_ip,

                "username":
                    "vagrant",

                "password":
                    "vagrant",

                "role":
                    machine["role"],

                "guacamole_url":
                    f"/guacamole/#/client/{vm_name}",
            }

        except Exception as e:

            print(
                f"[VM FAILED] {vm_name}"
            )

            print(str(e))

            try:

                run_cmd(

                    "vagrant destroy -f",

                    cwd=vm_dir,

                    timeout=1200
                )

            except:
                pass

            shutil.rmtree(

                vm_dir,

                ignore_errors=True
            )

            raise Exception(str(e))


# =========================================================
# VERIFY MACHINE
# =========================================================

def verify_machine(

    machine,

    verify_script
):

    ip = machine["ip"]

    ssh = paramiko.SSHClient()

    ssh.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )

    ssh.connect(

        ip,

        username="vagrant",

        password="vagrant"
    )

    remote_path = "/tmp/verify.sh"

    full_script = f"""#!/bin/bash

SCORE=0

set +e

{verify_script}

echo "FINAL_SCORE=$SCORE"
"""

    command = '''
echo vagrant | sudo -S bash /tmp/verify.sh
'''

    sftp = ssh.open_sftp()

    with sftp.file(
        remote_path,
        "w"
    ) as f:

        f.write(full_script)

    sftp.close()

    ssh.exec_command(
        f"chmod +x {remote_path}"
    )

    stdin, stdout, stderr = ssh.exec_command(
        command
    )

    output = stdout.read().decode(
        errors="ignore"
    )

    error = stderr.read().decode(
        errors="ignore"
    )

    ssh.close()

    full_output = (
        output +
        "\n" +
        error
    )

    match = re.search(

        r"FINAL_SCORE=(\d+)",

        full_output
    )

    score = (
        int(match.group(1))
        if match
        else 0
    )

    return {

        "score": score,

        "raw_output": full_output,
    }


# =========================================================
# DESTROY MACHINE
# =========================================================

def destroy_machine(
    vm_name
):

    vm_dir = (
        LABS_ROOT /
        vm_name
    )

    if not vm_dir.exists():

        return False

    result = run_cmd(

        "vagrant destroy -f",

        cwd=vm_dir,

        timeout=1200
    )

    print(result["stdout"])

    shutil.rmtree(

        vm_dir,

        ignore_errors=True
    )

    return True


# =========================================================
# CREATE FULL LAB FROM DJANGO TASK
# =========================================================

def create_lab(task_data):

    session_id = task_data["session_id"]

    variables = generate_variables(
        task_data["variable_schema"]
    )

    attacker_script = render_template(

        task_data["attacker_init_template"],

        variables
    )
    
    attacker_username = task_data.get(
        "attacker_username",
        random_username()
    )

    attacker_password = task_data.get(
        "attacker_password",
        random_password()
    )

    victim_username = task_data.get(
        "victim_username",
        random_username()
    )

    victim_password = task_data.get(
        "victim_password",
        random_password()
    )

    monitor_username = task_data.get(
        "monitor_username",
        random_username()
    )

    monitor_password = task_data.get(
        "monitor_password",
        random_password()
    )

    victim_script = render_template(

        task_data["victim_init_template"],

        variables
    )

    monitor_script = render_template(

        task_data["monitor_init_template"],

        variables
    )

    verify_script = render_template(

        task_data["verify_template"],

        variables
    )

    attacker_machine = {

        "role": "attacker",

        "vm_name":
            f"attacker-{session_id}",

        "base_box":
            "kalilinux/rolling",

        "memory_mb":
            2048,

        "cpu_count":
            2,

        "username":
            attacker_username,

        "password":
            attacker_password,
    }

    victim_machine = {

        "role": "victim",

        "vm_name":
            f"victim-{session_id}",

        "base_box":
            "generic/ubuntu2204",

        "memory_mb":
            1024,

        "cpu_count":
            1,

        "username":
            victim_username,

        "password":
            victim_password,
    }
    
    attacker_script = f"""
        useradd -m {attacker_username} || true

        echo '{attacker_username}:{attacker_password}' | chpasswd

        usermod -aG sudo {attacker_username}

        {attacker_script}
        """

    attacker = start_machine(

        attacker_machine,
        attacker_script
    )

    attacker["username"] = attacker_username
    attacker["password"] = attacker_password

    victim = start_machine(

        victim_machine,

        victim_script
    )
    victim["username"] = victim_username
    victim["password"] = victim_password

    return {

        "machines": [
            attacker,
            victim
        ],

        "variables":
            variables,

        "verify_script":
            verify_script,
    }