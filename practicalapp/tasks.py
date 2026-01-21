from celery import shared_task
from .models import PracticalSession
import uuid

@shared_task
def start_vm_task(session_id):
    session = PracticalSession.objects.get(id=session_id)
    session.vm_name = f"vm-{uuid.uuid4().hex[:8]}"
    session.vm_ip = "192.168.56.100"
    session.status = "running"
    session.save()
