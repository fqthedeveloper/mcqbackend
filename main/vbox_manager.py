# vbox_manager.py
import subprocess
import socket
import time
import logging
import random
import threading

logger = logging.getLogger(__name__)

# Path to VBoxManage.exe on Windows - change if different
VBOXMANAGE_PATH = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"

class VirtualBoxManager:
    def __init__(self, vboxmanage_path: str = VBOXMANAGE_PATH):
        self.vboxmanage_path = vboxmanage_path
        self.lock = threading.Lock()  # For thread safety

    def run_cmd(self, cmd, timeout=60):
        """
        Synchronously run a command and return stdout, or raise Exception with stderr.
        This is blocking and intended to be called from a thread or sync context.
        """
        logger.debug("Run: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            logger.debug("Cmd stderr: %s", proc.stderr.strip())
            raise Exception(proc.stderr.strip() or proc.stdout.strip())
        return proc.stdout.strip()

    def clone_vm(self, base_vm_name: str, new_vm_name: str, snapshot_name: str, ssh_port: int):
        """
        Clone VM from snapshot and configure NAT port-forward for SSH.
        Blocking — call from a thread.
        """
        with self.lock:
            # Check if base VM exists
            try:
                self.run_cmd([self.vboxmanage_path, "showvminfo", base_vm_name])
            except Exception as e:
                raise Exception(f"Base VM '{base_vm_name}' not found: {str(e)}")
            
            # Check if snapshot exists
            try:
                snapshots = self.run_cmd([self.vboxmanage_path, "snapshot", base_vm_name, "list"])
                if snapshot_name not in snapshots:
                    raise Exception(f"Snapshot '{snapshot_name}' not found in VM '{base_vm_name}'")
            except Exception as e:
                raise Exception(f"Error checking snapshots: {str(e)}")
            
            clone_cmd = [
                self.vboxmanage_path, "clonevm", base_vm_name,
                "--snapshot", snapshot_name,
                "--name", new_vm_name,
                "--register"
            ]
            self.run_cmd(clone_cmd)

            self.run_cmd([self.vboxmanage_path, "modifyvm", new_vm_name, "--nic1", "nat"])
            self.run_cmd([
                self.vboxmanage_path, "modifyvm", new_vm_name,
                "--natpf1", f"guestssh,tcp,,{ssh_port},,22"
            ])
            logger.info("Cloned VM %s from %s snapshot %s (ssh_port=%s)", new_vm_name, base_vm_name, snapshot_name, ssh_port)
            return True

    def start_vm(self, vm_name: str, headless: bool = True):
        with self.lock:
            # Check if VM exists
            try:
                self.run_cmd([self.vboxmanage_path, "showvminfo", vm_name])
            except Exception as e:
                raise Exception(f"VM '{vm_name}' not found: {str(e)}")
                
            typ = "headless" if headless else "gui"
            self.run_cmd([self.vboxmanage_path, "startvm", vm_name, "--type", typ])
            logger.info("Started VM %s", vm_name)
            return True

    def stop_vm(self, vm_name: str, force: bool = True):
        with self.lock:
            # Check if VM exists first
            try:
                self.run_cmd([self.vboxmanage_path, "showvminfo", vm_name])
            except Exception:
                logger.warning("VM %s not found for stopping", vm_name)
                return False
                
            if force:
                try:
                    self.run_cmd([self.vboxmanage_path, "controlvm", vm_name, "poweroff"])
                except Exception as e:
                    logger.warning("poweroff failed: %s", e)
            else:
                try:
                    self.run_cmd([self.vboxmanage_path, "controlvm", vm_name, "acpipowerbutton"])
                except Exception as e:
                    logger.warning("acpi failed: %s", e)
            return True

    def delete_vm(self, vm_name: str):
        try:
            with self.lock:
                # Check if VM exists first
                try:
                    self.run_cmd([self.vboxmanage_path, "showvminfo", vm_name])
                except Exception:
                    logger.warning("VM %s not found for deletion", vm_name)
                    return True
                    
                self.stop_vm(vm_name, force=True)
                time.sleep(1)
                self.run_cmd([self.vboxmanage_path, "unregistervm", vm_name, "--delete"])
                logger.info("Deleted VM %s", vm_name)
                return True
        except Exception as e:
            logger.error("delete_vm error: %s", e)
            return False

    def get_vm_info(self, vm_name: str):
        try:
            with self.lock:
                out = self.run_cmd([self.vboxmanage_path, "showvminfo", vm_name, "--machinereadable"])
                info = {}
                for line in out.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        info[k.strip()] = v.strip().strip('"')
                return info
        except Exception as e:
            logger.warning("get_vm_info for %s: %s", vm_name, e)
            return {}

    def list_vms(self):
        with self.lock:
            out = self.run_cmd([self.vboxmanage_path, "list", "vms"])
            vms = []
            for line in out.splitlines():
                if '"' in line:
                    parts = line.split('"')
                    if len(parts) > 1:
                        vms.append(parts[1])
            return vms

    def wait_for_vm_boot(self, vm_name: str, ssh_port: int, timeout: int = 180, interval: float = 2.0):
        """
        Wait until VM is reported running and forwarded SSH port accepts TCP.
        Blocking — call from a thread or sync context.
        """
        start = time.time()
        while time.time() - start < timeout:
            # Check VM state
            try:
                info = self.get_vm_info(vm_name)
                state = info.get("VMState", "")
                if state == "running":
                    try:
                        with socket.create_connection(("127.0.0.1", int(ssh_port)), timeout=2):
                            logger.info("SSH port %s responsive for %s", ssh_port, vm_name)
                            return True
                    except Exception:
                        pass
                elif state in ("poweroff", "aborted"):
                    # VM is not running, no point waiting
                    break
            except Exception:
                # VM info not available
                pass
                
            time.sleep(interval)
            
        logger.warning("VM %s did not boot or SSH not open on port %s within %s seconds", vm_name, ssh_port, timeout)
        return False

# Global instance for import
vbox_manager = VirtualBoxManager()