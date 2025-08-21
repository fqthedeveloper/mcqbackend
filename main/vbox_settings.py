import subprocess
import json
import time
import logging
import os
from django.conf import settings

logger = logging.getLogger(__name__)

class VirtualBoxManager:
    def __init__(self):
        self.vm_base_name = "Redhat"
        self.vboxmanage_path = self._get_vboxmanage_path()
        
    def _get_vboxmanage_path(self):
        # Try to find VBoxManage in common locations
        possible_paths = [
            "VBoxManage",
            "/usr/bin/VBoxManage",
            "/usr/local/bin/VBoxManage",
            "C:\\Program Files\\Oracle\\VirtualBox\\VBoxManage.exe"
        ]
        
        for path in possible_paths:
            try:
                subprocess.run([path, "--version"], capture_output=True, check=True)
                return path
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
                
        raise Exception("VBoxManage not found. Please install VirtualBox and ensure it's in your PATH")
    
    def clone_vm(self, new_vm_name, snapshot_name="base_snapshot"):
        """Clone the base VM to create a new instance"""
        try:
            # Check if base VM exists
            check_cmd = [self.vboxmanage_path, "showvminfo", self.vm_base_name, "--machinereadable"]
            result = subprocess.run(check_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"Base VM '{self.vm_base_name}' not found")
            
            # Clone the VM
            clone_cmd = [
                self.vboxmanage_path, "clonevm", self.vm_base_name,
                "--name", new_vm_name,
                "--register",
                "--mode", "machine",
                "--options", "keepallmacs"
            ]
            
            # Use snapshot if specified
            if snapshot_name:
                clone_cmd.extend(["--snapshot", snapshot_name])
                
            result = subprocess.run(clone_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"Failed to clone VM: {result.stderr}")
                
            logger.info(f"Successfully cloned VM: {new_vm_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error cloning VM: {str(e)}")
            return False
    
    def start_vm(self, vm_name, headless=True):
        """Start a VM"""
        try:
            mode = "headless" if headless else "gui"
            cmd = [self.vboxmanage_path, "startvm", vm_name, "--type", mode]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Failed to start VM: {result.stderr}")
                
            logger.info(f"Successfully started VM: {vm_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error starting VM: {str(e)}")
            return False
    
    def stop_vm(self, vm_name, force=False):
        """Stop a VM gracefully or forcefully"""
        try:
            if force:
                cmd = [self.vboxmanage_path, "controlvm", vm_name, "poweroff"]
            else:
                cmd = [self.vboxmanage_path, "controlvm", vm_name, "acpipowerbutton"]
                
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Failed to stop VM: {result.stderr}")
                
            logger.info(f"Successfully stopped VM: {vm_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping VM: {str(e)}")
            return False
    
    def delete_vm(self, vm_name):
        """Completely remove a VM"""
        try:
            # First power off if running
            self.stop_vm(vm_name, force=True)
            
            # Unregister and delete
            cmd = [self.vboxmanage_path, "unregistervm", vm_name, "--delete"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Failed to delete VM: {result.stderr}")
                
            logger.info(f"Successfully deleted VM: {vm_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting VM: {str(e)}")
            return False
    
    def get_vm_info(self, vm_name):
        """Get information about a VM"""
        try:
            cmd = [self.vboxmanage_path, "showvminfo", vm_name, "--machinereadable"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Failed to get VM info: {result.stderr}")
                
            info = {}
            for line in result.stdout.splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    info[key] = value.strip('"')
                    
            return info
            
        except Exception as e:
            logger.error(f"Error getting VM info: {str(e)}")
            return None
    
    def set_network_nat(self, vm_name):
        """Configure NAT network for the VM"""
        try:
            cmd = [
                self.vboxmanage_path, "modifyvm", vm_name,
                "--nic1", "nat",
                "--natpf1", "guestssh,tcp,,2222,,22"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Failed to configure NAT: {result.stderr}")
                
            logger.info(f"Successfully configured NAT for VM: {vm_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring NAT: {str(e)}")
            return False
    
    def execute_command_in_vm(self, vm_name, command, username="examuser", password="exampass", timeout=30):
        """Execute a command inside the VM using SSH"""
        try:
            # Get VM IP (assuming NAT network with port forwarding)
            # For simplicity, we'll use localhost with port forwarding
            ssh_cmd = [
                "sshpass", "-p", password,
                "ssh", "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-p", "2222",
                f"{username}@localhost",
                command
            ]
            
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
            
            if result.returncode != 0:
                raise Exception(f"Command failed: {result.stderr}")
                
            return result.stdout
            
        except subprocess.TimeoutExpired:
            raise Exception("Command execution timed out")
        except Exception as e:
            raise Exception(f"Error executing command: {str(e)}")
    
    def wait_for_vm_boot(self, vm_name, timeout=120):
        """Wait for VM to boot and become responsive"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Try to execute a simple command to check if VM is responsive
                self.execute_command_in_vm(vm_name, "echo 'VM is ready'", timeout=10)
                return True
            except:
                time.sleep(5)
                
        raise Exception(f"VM {vm_name} did not become responsive within {timeout} seconds")

# Global instance
vbox_manager = VirtualBoxManager()