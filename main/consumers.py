import json
import logging
import asyncio
import threading
import time
import urllib.parse
import paramiko
from io import StringIO

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings

from .models import PracticalExamSession

logger = logging.getLogger(__name__)

class PracticalTerminalConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ssh_client = None
        self.ssh_channel = None
        self.session = None
        self.connected = False

    def get_token_from_query(self):
        qs = self.scope.get('query_string', b'').decode()
        params = urllib.parse.parse_qs(qs)
        return params.get('token', [None])[0]

    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.token = self.get_token_from_query()
        
        if not self.token:
            await self.close(code=4001)
            return

        self.session = await self.get_session()
        if not self.session:
            await self.close(code=4003)
            return

        # Connect to VM via SSH
        if not await self.connect_to_vm():
            await self.close(code=4005)
            return

        self.connected = True
        await self.accept()

    async def disconnect(self, close_code):
        self.connected = False
        if self.ssh_channel:
            self.ssh_channel.close()
        if self.ssh_client:
            self.ssh_client.close()

    async def receive(self, text_data=None, bytes_data=None):
        if not self.connected or not self.ssh_channel:
            return

        try:
            data = bytes_data if bytes_data is not None else text_data.encode('utf-8')
            self.ssh_channel.send(data)
        except Exception as e:
            logger.error(f"Error sending data to SSH: {str(e)}")
            await self.close(code=4006)

    async def connect_to_vm(self):
        try:
            # Create SSH client
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect to VM (using localhost with port forwarding)
            self.ssh_client.connect(
                'localhost',
                port=2222,
                username=self.session.exam.vm_username,
                password=self.session.exam.vm_password,
                timeout=30
            )
            
            # Create interactive shell
            self.ssh_channel = self.ssh_client.invoke_shell(term='xterm-256color')
            self.ssh_channel.setblocking(False)
            
            # Start thread to read from SSH channel
            self.read_thread = threading.Thread(target=self.read_ssh_output, daemon=True)
            self.read_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"SSH connection failed: {str(e)}")
            return False

    def read_ssh_output(self):
        while self.connected:
            try:
                if self.ssh_channel and self.ssh_channel.recv_ready():
                    data = self.ssh_channel.recv(4096)
                    if data:
                        asyncio.run(self.send_output(data))
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Error reading SSH output: {str(e)}")
                break

    async def send_output(self, data):
        try:
            await self.send(bytes_data=data)
        except Exception as e:
            logger.error(f"Error sending output to WebSocket: {str(e)}")

    @database_sync_to_async
    def get_session(self):
        try:
            return PracticalExamSession.objects.get(
                id=self.session_id,
                token=self.token,
                status='running'
            )
        except PracticalExamSession.DoesNotExist:
            return None