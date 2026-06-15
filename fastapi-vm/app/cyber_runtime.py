import os
import re
import sys
import json
import time
import shutil
import random
import socket
import string
import threading
import subprocess

from pathlib import Path

import paramiko
from .cyber_guacamole import create_guacamole_connection


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

            elapsed = (
                time.time() - start_time
            )

            if elapsed > timeout:

                process.kill()

                raise Exception(
                    f"Timeout: {cmd}"
                )

    remaining = process.stdout.read()

    if remaining:

        output_lines.append(
            remaining
        )

    output = "".join(
        output_lines
    )

    return {

        "stdout": output,

        "returncode":
            process.returncode,
    }


# =========================================================
# CLEANUP
# =========================================================

def cleanup_old_labs():

    if LABS_ROOT.exists():

        shutil.rmtree(

            LABS_ROOT,

            ignore_errors=True
        )

    LABS_ROOT.mkdir(
        exist_ok=True
    )


# =========================================================
# REMOVE OLD VMS
# =========================================================

def remove_old_vms():

    result = run_cmd(
        "VBoxManage list vms"
    )

    for line in result["stdout"].splitlines():

        if "attacker-" in line:

            try:

                vm_name = (
                    line.split("{")[0]
                    .replace('"', '')
                    .strip()
                )

                run_cmd(

                    f'VBoxManage controlvm "{vm_name}" poweroff'
                )

                run_cmd(

                    f'VBoxManage unregistervm "{vm_name}" --delete'
                )

            except:
                pass


# =========================================================
# ALLOCATE IP
# =========================================================

def allocate_ip():

    return (
        f"{VM_IP_BASE}"
        f"{random.randint(50,240)}"
    )


# =========================================================
# BUILD VAGRANTFILE
# =========================================================

# =========================================================
# BUILD VAGRANTFILE
# =========================================================

def build_vagrantfile(machine):

    vm_name = machine["vm_name"]

    vm_ip = machine["ip"]

    base_box = machine["base_box"]

    memory = machine["memory_mb"]

    cpus = machine["cpu_count"]

    return f'''
Vagrant.configure("2") do |config|

  # =====================================================
  # BASIC
  # =====================================================

  config.vm.box = "{base_box}"

  config.vm.hostname = "{vm_name}"

  # =====================================================
  # DISABLE SHARED FOLDER
  # =====================================================

  config.vm.synced_folder ".", "/vagrant", disabled: true

  # =====================================================
  # NETWORK
  # =====================================================

  config.vm.network "private_network", ip: "{vm_ip}"

  # =====================================================
  # SSH
  # =====================================================

  config.vm.boot_timeout = 1800

  config.ssh.username = "vagrant"

  config.ssh.password = "vagrant"

  config.ssh.insert_key = false

  config.ssh.keep_alive = true

  # =====================================================
  # VIRTUALBOX
  # =====================================================

  config.vm.provider "virtualbox" do |vb|

    # HEADLESS MODE

    vb.gui = false

    # VM NAME

    vb.name = "{vm_name}"

    # RESOURCES

    vb.memory = "{memory}"

    vb.cpus = {cpus}

    # ===================================================
    # VRAM FIX
    # ===================================================

    vb.customize [
      "modifyvm",
      :id,
      "--graphicscontroller",
      "vboxsvga"
    ]

    vb.customize [
      "modifyvm",
      :id,
      "--vram",
      "16"
    ]

    vb.customize [
      "modifyvm",
      :id,
      "--accelerate3d",
      "off"
    ]

    # ===================================================
    # PERFORMANCE
    # ===================================================

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
      "--usb",
      "off"
    ]

    vb.customize [
      "modifyvm",
      :id,
      "--usbehci",
      "off"
    ]

    vb.customize [
      "modifyvm",
      :id,
      "--nictype1",
      "virtio"
    ]

  end

end
'''


# =========================================================
# WAIT SSH
# =========================================================

def wait_for_ssh(ip):

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

                timeout=10,

                allow_agent=False,

                look_for_keys=False
            )

            ssh.close()

            return True

        except:

            time.sleep(10)

    raise Exception(
        f"SSH timeout: {ip}"
    )


# =========================================================
# RUN INIT SCRIPT
# =========================================================

def run_init_script(
    ip,
    script
):

    ssh = paramiko.SSHClient()

    ssh.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )

    ssh.connect(

        ip,

        username="vagrant",

        password="vagrant",

        allow_agent=False,

        look_for_keys=False
    )

    sftp = ssh.open_sftp()

    remote_path = "/tmp/init.sh"

    with sftp.file(
        remote_path,
        "w"
    ) as f:

        f.write(f'''
#!/bin/bash

set -e
set -x

{script}
''')

    sftp.close()

    ssh.exec_command(
        "chmod +x /tmp/init.sh"
    )

    stdin, stdout, stderr = ssh.exec_command(
        "sudo bash /tmp/init.sh",
        get_pty=True
    )

    output = stdout.read().decode()

    error = stderr.read().decode()

    ssh.close()

    print(output)

    print(error)


# =========================================================
# START MACHINE
# =========================================================

def start_machine(
    machine,
    init_script
):

    vm_name = machine["vm_name"]

    vm_dir = (
        LABS_ROOT /
        vm_name
    )

    vm_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    ensure = run_cmd(
        "VBoxManage --version"
    )

    if ensure["returncode"] != 0:

        raise Exception(
            "VirtualBox not installed"
        )

    machine["ip"] = allocate_ip()

    vm_ip = machine["ip"]

    vagrantfile = build_vagrantfile(
        machine
    )

    with open(

        vm_dir / "Vagrantfile",

        "w",

        encoding="utf-8"

    ) as f:

        f.write(vagrantfile)

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

    wait_for_ssh(
        machine["ip"]
    )

    run_init_script(

        machine["ip"],

        init_script
    )

    # =========================================================
    # CREATE GUACAMOLE CONNECTION
    # =========================================================

    try:

        print(f"[GUACAMOLE] Creating connection for {vm_name}")

        guac = create_guacamole_connection(
            vm_name=vm_name,
            vm_ip=machine["ip"],
            username="vagrant",
            password="vagrant",
            os_type="linux"
        )

        print(f"[GUACAMOLE] SUCCESS")

        print(guac)

    except Exception as e:

        print(f"[GUACAMOLE ERROR]")

        print(str(e))

        guac = {

            "connection_id": "",

            "url": ""
        }

    # =========================================================
    # RETURN MACHINE
    # =========================================================

    return {

        "vm_name":
            vm_name,

        "vm_ip":
            vm_ip,

        "username":
            machine.get(
                "username",
                "vagrant"
            ),

        "password":
            machine.get(
                "password",
                "vagrant"
            ),

        "role":
            machine["role"],

        "guacamole_connection_id":
            str(
                guac.get(
                    "connection_id",
                    ""
                )
            ),

        "guacamole_url":
            guac.get(
                "url",
                ""
            ),
    }

# =========================================================
# START LAB
# =========================================================

def start_cyber_lab(

    session_id,

    variables,

    attacker_script,

    victim_script,

    monitor_script,

    attacker_username,

    attacker_password,

    victim_username,

    victim_password,

    monitor_username=None,

    monitor_password=None,
):

    print("=" * 60)
    print(f"[SESSION {session_id}] START CYBER LAB")
    print("=" * 60)

    cleanup_old_labs()

    remove_old_vms()

    machines = []

    # =====================================================
    # ATTACKER
    # =====================================================

    attacker_cfg = variables.get(
        "attacker",
        {}
    )

    attacker_machine = {

        "role": "attacker",

        "vm_name":
            f"attacker-{session_id}",

        "base_box":
            attacker_cfg.get(
                "base_box",
                "kalilinux/rolling"
            ),

        "memory_mb":
            attacker_cfg.get(
                "memory_mb",
                2048
            ),

        "cpu_count":
            attacker_cfg.get(
                "cpu_count",
                2
            ),
    }

    print(
        f"[SESSION {session_id}] Starting Attacker VM"
    )

    attacker = start_machine(
        attacker_machine,
        attacker_script
    )

    machines.append(
        attacker
    )

    print(
        f"[SESSION {session_id}] Attacker Ready"
    )

    # =====================================================
    # VICTIM
    # =====================================================

    victim_cfg = variables.get(
        "victim",
        {}
    )

    if victim_cfg:

        victim_machine = {

            "role": "victim",

            "vm_name":
                f"victim-{session_id}",

            "base_box":
                victim_cfg.get(
                    "base_box",
                    "generic/ubuntu2204"
                ),

            "memory_mb":
                victim_cfg.get(
                    "memory_mb",
                    2048
                ),

            "cpu_count":
                victim_cfg.get(
                    "cpu_count",
                    2
                ),
        }

        print(
            f"[SESSION {session_id}] Starting Victim VM"
        )

        victim = start_machine(
            victim_machine,
            victim_script
        )

        machines.append(
            victim
        )

        print(
            f"[SESSION {session_id}] Victim Ready"
        )

    # =====================================================
    # MONITOR
    # =====================================================

    monitor_cfg = variables.get(
        "monitor",
        {}
    )

    if monitor_cfg:

        monitor_machine = {

            "role": "monitor",

            "vm_name":
                f"monitor-{session_id}",

            "base_box":
                monitor_cfg.get(
                    "base_box",
                    "generic/ubuntu2204"
                ),

            "memory_mb":
                monitor_cfg.get(
                    "memory_mb",
                    2048
                ),

            "cpu_count":
                monitor_cfg.get(
                    "cpu_count",
                    2
                ),
        }

        print(
            f"[SESSION {session_id}] Starting Monitor VM"
        )

        monitor = start_machine(
            monitor_machine,
            monitor_script
        )

        machines.append(
            monitor
        )

        print(
            f"[SESSION {session_id}] Monitor Ready"
        )

    print("=" * 60)
    print(
        f"[SESSION {session_id}] ALL MACHINES READY"
    )
    print("=" * 60)

    return {

        "success": True,

        "session_id":
            session_id,

        "machines":
            machines,

        "message":
            "Cyber lab started successfully",
    }



# =========================================================
# DESTROY
# =========================================================

def destroy_cyber_lab(
    session_id
):

    vm_names = [

        f"attacker-{session_id}",

        f"victim-{session_id}",

        f"monitor-{session_id}",
    ]

    for vm_name in vm_names:

        vm_dir = (
            LABS_ROOT /
            vm_name
        )

        if vm_dir.exists():

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

    return {

        "success": True,

        "message":
            "Cyber lab destroyed"
    }