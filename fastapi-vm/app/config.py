import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

VAGRANT_BASE_BOX = "rockylinux/8"
VAGRANT_VM_ROOT = os.path.join(BASE_DIR, "vms")
HISTORY_ROOT = os.path.join(BASE_DIR, "vms_history")

VM_USER = "kiosk"
VM_PASSWORD = "redhat"

SSH_TIMEOUT = 20

VM_IP_BASE = "192.168.56."
VM_IP_START = 100

EXTRA_DISKS = [
    {"name": "disk1.vdi", "size_mb": 5120},
]