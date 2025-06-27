# tasks.py
from datetime import timedelta
from celery import shared_task
import docker
from django.utils import timezone

from main.views import get_docker_client
from .models import ExamSession, PracticalExamSession
import logging

logger = logging.getLogger(__name__)

@shared_task
def cleanup_expired_containers():
    try:
        client = get_docker_client()
        cutoff = timezone.now() - timedelta(hours=6)
        
        expired_sessions = PracticalExamSession.objects.filter(
            status='running',
            start_time__lt=cutoff
        )
        
        for session in expired_sessions:
            try:
                container = client.containers.get(session.container_id)
                container.stop(timeout=5)
                container.remove()
            except docker.errors.NotFound:
                pass  # Already removed
            except Exception as e:
                logger.error(f"Cleanup error: {str(e)}")
            
            session.status = 'terminated'
            session.termination_reason = 'System timeout'
            session.save()
            
        logger.info(f"Cleaned up {expired_sessions.count()} expired sessions")
        
    except Exception as e:
        logger.error(f"Cleanup task failed: {str(e)}")