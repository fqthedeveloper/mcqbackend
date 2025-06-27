# consumers.py
import json
import logging
import asyncio
from django.conf import settings
import docker
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import PracticalExamSession

logger = logging.getLogger(__name__)

class PracticalTerminalConsumer(AsyncWebsocketConsumer):
    container = None
    exec_id = None
    socket_reader = None
    
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        query_params = self.scope['query_string'].decode()
        token = None
        
        if 'session_token=' in query_params:
            token = query_params.split('session_token=')[1].split('&')[0]
        
        if not token:
            await self.close(code=4001)
            return
            
        session = await self.get_session(token)
        if not session:
            await self.close(code=4003)
            return
            
        try:
            self.docker_client = docker.from_env()
            
            if not session.container_id:
                session = await self.start_container(session)
            
            self.container = self.docker_client.containers.get(session.container_id)
            self.exec_id = self.container.exec_run(
                "/bin/bash",
                stdin=True,
                stdout=True,
                stderr=True,
                tty=True,
                socket=True,
                detach=True
            )
            
            self.socket_reader = True
            await self.accept()
            await self.send_initial_message()
            asyncio.create_task(self.read_socket_output())
        except docker.errors.NotFound:
            logger.error(f"Container not found for session {self.session_id}")
            await self.send(text_data=json.dumps({
                'type': 'system',
                'message': '❌ Container not found. Please restart the exam.'
            }))
            await self.close(code=4002)
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'system',
                'message': f'❌ Connection failed: {str(e)}'
            }))
            await self.close(code=4003)

    async def disconnect(self, close_code):
        self.socket_reader = False
        if self.exec_id:
            try:
                self.exec_id.close()
            except:
                pass

    async def read_socket_output(self):
        while self.socket_reader:
            try:
                if self.exec_id.output and self.exec_id.output._sock:
                    try:
                        data = self.exec_id.output._sock.recv(1024)
                        if data:
                            await self.send(bytes_data=data)
                        else:
                            await asyncio.sleep(0.1)
                    except BlockingIOError:
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        logger.error(f"Error reading from socket: {str(e)}")
                        break
                else:
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Socket read error: {str(e)}")
                await self.send(text_data=json.dumps({
                    'type': 'system',
                    'message': f'❌ Terminal error: {str(e)}'
                }))
                break

    @database_sync_to_async
    def get_session(self, token):
        try:
            return PracticalExamSession.objects.get(
                id=self.session_id,
                token=token,
                status='running'
            )
        except PracticalExamSession.DoesNotExist:
            return None
    
    @database_sync_to_async
    def start_container(self, session):
        try:
            container = self.docker_client.containers.run(
                session.exam.docker_image,
                command="sleep infinity",
                detach=True,
                tty=True,
                stdin_open=True,
                environment={
                    **session.exam.environment_vars,
                    "STUDENT_ID": str(session.student.id),
                    "EXAM_ID": str(session.exam.id)
                },
                volumes={
                    f"{settings.BASE_DIR}/exam_data/{session.id}": {
                        'bind': '/exam', 
                        'mode': 'rw'
                    }
                },
                name=f"practical-exam-{session.id}",
            )
            
            if session.exam.setup_command:
                exit_code, output = container.exec_run(
                    f"sh -c '{session.exam.setup_command}'",
                    workdir="/exam",
                    tty=True
                )
                logger.info(f"Setup command executed: {exit_code}")
            
            session.container_id = container.id
            session.save()
            return session
        except docker.errors.ImageNotFound:
            logger.error(f"Image not found: {session.exam.docker_image}")
            raise Exception(f"Exam environment image not available.")
        except docker.errors.APIError as e:
            logger.error(f"Docker API error: {str(e)}")
            raise Exception("Failed to start exam environment.")
        except Exception as e:
            logger.exception("Container start failed")
            raise Exception("Container startup failed")
    
    async def send_initial_message(self):
        await self.send(text_data=json.dumps({
            'type': 'system',
            'message': '🚀 Connected to exam environment. Start working on your tasks...'
        }))
    
    async def receive(self, text_data=None, bytes_data=None):
        try:
            if text_data:
                try:
                    data = json.loads(text_data)
                    if data.get('type') == 'resize':
                        cols = data.get('cols', 80)
                        rows = data.get('rows', 24)
                        if self.exec_id:
                            self.exec_id.resize(cols, rows)
                        return
                except:
                    pass
                
                if self.exec_id and self.exec_id.output and self.exec_id.output._sock:
                    self.exec_id.output._sock.send(text_data.encode('utf-8'))
            elif bytes_data:
                if self.exec_id and self.exec_id.output and self.exec_id.output._sock:
                    self.exec_id.output._sock.send(bytes_data)
        except Exception as e:
            logger.error(f"Error handling data: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'system',
                'message': f'❌ Command error: {str(e)}'
            }))