# tasks.py
from celery import shared_task
import docker
from django.utils import timezone
from .models import ExamSession
import logging

logger = logging.getLogger(__name__)

@shared_task
def cleanup_expired_containers():
    try:
        client = docker.from_env()
        expired_sessions = ExamSession.objects.filter(
            is_completed=False,
            start_time__lt=timezone.now() - timezone.timedelta(hours=6)
        ).exclude(container_id='')

        for session in expired_sessions:
            try:
                container = client.containers.get(session.container_id)
                container.stop()
                container.remove()
                try:
                    client.volumes.get(f'exam-home-{session.id}').remove()
                except:
                    pass
            except docker.errors.NotFound:
                pass
            except Exception as e:
                logger.error(f"Container cleanup error for session {session.id}: {str(e)}")
            
            session.container_id = ''
            session.termination_reason = 'Automated cleanup'
            session.save()
    except Exception as e:
        logger.error(f"Container cleanup task error: {str(e)}")