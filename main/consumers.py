# consumers.py
import json
import logging
import docker
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework.authtoken.models import Token
from .models import ExamSession, PracticalTask, PracticalAnswer

logger = logging.getLogger(__name__)

class PracticalTerminalConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.user = AnonymousUser()
        
        # Authenticate via token
        token_key = None
        for item in self.scope['query_string'].decode().split('&'):
            if item.startswith('token='):
                token_key = item.split('=')[1]
                break
        
        if token_key:
            try:
                token = await sync_to_async(Token.objects.get)(key=token_key)
                self.user = token.user
            except Token.DoesNotExist:
                pass
        
        if not self.user.is_authenticated or self.user.user_type != 'student':
            await self.close()
            return
        
        # Get exam session
        try:
            self.session = await sync_to_async(ExamSession.objects.get)(
                id=self.session_id,
                student=self.user,
                is_completed=False
            )
        except ExamSession.DoesNotExist:
            await self.close()
            return
        
        # Start container if not running
        if not self.session.container_id:
            try:
                await sync_to_async(self.start_container)()
            except Exception as e:
                logger.error(f"Failed to start container: {str(e)}")
                await self.close()
                return
        
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connection',
            'message': f'Connected to practical terminal for session {self.session_id}'
        }))

    async def disconnect(self, close_code):
        pass

    def start_container(self):
        environment = self.session.exam.environments.first()
        if not environment:
            raise Exception("No Docker environment configured")
        
        client = docker.from_env()
        container = client.containers.run(
            environment.image,
            command="/bin/bash",
            detach=True,
            tty=True,
            stdin_open=True,
            name=f"exam-session-{self.session.id}",
            network_mode='none',
            mem_limit='1g',
            cpu_period=50000,
            cpu_quota=25000,
            volumes={
                f'exam-home-{self.session.id}': {'bind': '/home/user', 'mode': 'rw'}
            },
            user='user'
        )
        
        # Run setup script
        exit_code, output = container.exec_run(
            f"bash -c '{environment.setup_script}'",
            user='root'
        )
        
        if exit_code != 0:
            container.stop()
            container.remove()
            raise Exception("Setup script failed")
        
        self.session.container_id = container.id
        self.session.save()

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            
            if data['type'] == 'command':
                command = data['command'].strip()
                task_id = data.get('task_id')
                
                if not command:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'output': '\r\nError: Empty command not allowed\r\n'
                    }))
                    return
                
                # Block dangerous commands
                blocked_commands = [
                    'rm ', 'shutdown', 'reboot', 'dd ', 'mkfs', 
                    ':(){:|:&};:', 'mv ', '> ', 'chmod', 'sudo',
                    'passwd', 'useradd', 'groupadd', 'visudo'
                ]
                if any(cmd in command for cmd in blocked_commands):
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'output': '\r\nError: Blocked command for security reasons\r\n'
                    }))
                    return
                
                # Execute command in container
                result = await sync_to_async(self.execute_in_container)(command, task_id)
                
                if result['status'] == 'success':
                    await self.send(text_data=json.dumps({
                        'type': 'command_output',
                        'output': result['output']
                    }))
                else:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'output': f"\r\nError: {result['error']}\r\n"
                    }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'output': '\r\nError: Invalid JSON format\r\n'
            }))

    def execute_in_container(self, command, task_id=None):
        if not self.session.container_id:
            return {'status': 'error', 'error': 'Container not running'}
        
        try:
            client = docker.from_env()
            container = client.containers.get(self.session.container_id)
            
            # Execute command
            exit_code, output = container.exec_run(
                f"/bin/bash -c '{command}'",
                user='user',
                workdir='/home/user',
                environment={'TERM': 'xterm-256color'},
                demux=True
            )
            
            # Decode output
            stdout, stderr = output
            stdout = stdout.decode('utf-8') if stdout else ''
            stderr = stderr.decode('utf-8') if stderr else ''
            combined_output = stdout + stderr
            
            # Save answer if task specified
            if task_id:
                try:
                    task = PracticalTask.objects.get(id=task_id)
                    PracticalAnswer.objects.update_or_create(
                        session=self.session,
                        task=task,
                        defaults={
                            'command_used': command,
                            'output': combined_output
                        }
                    )
                except PracticalTask.DoesNotExist:
                    pass
            
            return {
                'status': 'success',
                'output': combined_output,
                'exit_code': exit_code
            }
        except docker.errors.NotFound:
            return {'status': 'error', 'error': 'Container not found'}
        except docker.errors.DockerException as e:
            logger.error(f"Docker error: {str(e)}")
            return {'status': 'error', 'error': f'Docker error: {str(e)}'}