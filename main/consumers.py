import json
import subprocess
import re
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from asgiref.sync import sync_to_async
from rest_framework.authtoken.models import Token
from django.core.exceptions import ObjectDoesNotExist
from .models import ExamSession, Exam, PracticalTask, PracticalAnswer

logger = logging.getLogger(__name__)

class PracticalTerminalConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.user = AnonymousUser()
        
        query_params = self.scope.get('query_string', b'').decode().split('&')
        token_key = None
        exam_id = None
        
        for param in query_params:
            if '=' in param:
                key, value = param.split('=', 1)
                if key == 'token':
                    token_key = value
                elif key == 'exam_id':
                    exam_id = value
        
        if not token_key:
            await self.close(code=4001)
            return
            
        try:
            token = await sync_to_async(Token.objects.get)(key=token_key)
            self.user = token.user
        except Token.DoesNotExist:
            await self.close(code=4001)
            return
        
        if self.user.user_type != 'student':
            await self.close(code=4001)
            return
        
        if not exam_id:
            await self.close(code=4002)
            return
        
        try:
            self.session = await sync_to_async(ExamSession.objects.get)(
                id=int(self.session_id),
                student=self.user
            )
            if self.session.is_completed:
                await self.close(code=4003)
                return
                
        except (ObjectDoesNotExist, ValueError):
            try:
                exam = await sync_to_async(Exam.objects.get)(id=int(exam_id))
                if exam.mode == 'practical':
                    try:
                        self.session = await sync_to_async(ExamSession.objects.get)(id=int(self.session_id))
                    except ExamSession.DoesNotExist:
                        self.session = await sync_to_async(ExamSession.objects.create)(
                            id=int(self.session_id),
                            student=self.user,
                            exam=exam,
                            is_completed=False
                        )
                else:
                    await self.close(code=4002)
                    return
            except (Exam.DoesNotExist, ValueError):
                await self.close(code=4002)
                return
        
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connection',
            'message': f'Connected to practical terminal for session {self.session_id}'
        }))

    async def disconnect(self, close_code):
        pass

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
                
                blocked_commands = ['rm ', 'shutdown', 'reboot', 'dd ', 'mkfs', 
                                   ':(){:|:&};:', 'mv ', '> ', 'chmod', 'sudo']
                if any(cmd in command for cmd in blocked_commands):
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'output': '\r\nError: Blocked command for security reasons\r\n'
                    }))
                    return
                
                try:
                    process = subprocess.Popen(
                        command,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    stdout, stderr = process.communicate(timeout=30)
                    output = stdout + stderr
                    
                    await self.send(text_data=json.dumps({
                        'type': 'command_output',
                        'output': output
                    }))
                    
                    if task_id:
                        await self.save_answer(command, output, task_id)
                except subprocess.TimeoutExpired:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'output': '\r\nError: Command timed out after 30 seconds\r\n'
                    }))
                except Exception as e:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'output': f"\r\nError: {str(e)}\r\n"
                    }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'output': '\r\nError: Invalid JSON format\r\n'
            }))

    async def save_answer(self, command, output, task_id):
        try:
            task = await sync_to_async(PracticalTask.objects.get)(id=task_id)
            
            answer, created = await sync_to_async(PracticalAnswer.objects.update_or_create)(
                session=self.session,
                task=task,
                defaults={
                    'command_used': command,
                    'output': output
                }
            )
        except PracticalTask.DoesNotExist:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'output': f"\r\nError: Invalid task ID: {task_id}\r\n"
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'output': f"\r\nSave error: {str(e)}\r\n"
            }))