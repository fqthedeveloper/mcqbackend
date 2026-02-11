import asyncio
import json
import paramiko
from channels.generic.websocket import AsyncWebsocketConsumer

class SSHConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        from .models import PracticalSession
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.user = self.scope.get("user")
        await self.accept()
        
        self.session = await asyncio.to_thread(PracticalSession.objects.get, pk=self.session_id)
        self.running = True
        self.ssh = None
        self.channel = None
        await asyncio.to_thread(self.start_ssh)
        asyncio.create_task(self.read_ssh())

    def start_ssh(self):
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(
                hostname=self.session.vm_ip, 
                username="vagrant", 
                password="vagrant"
            )
            self.channel = self.ssh.invoke_shell(term="xterm-256color", width=80, height=24)
            self.channel.settimeout(0.0)
            # Standard bash init
            self.channel.send("export TERM=xterm-256color\nclear\nsudo -iu kiosk\nclear\n")
        except Exception as e:
            print(f"SSH Error: {e}")

    async def read_ssh(self):
        while self.running:
            if self.channel and self.channel.recv_ready():
                data = await asyncio.to_thread(self.channel.recv, 8192)
                await self.send(bytes_data=data)
            await asyncio.sleep(0.01)

    async def receive(self, text_data=None, bytes_data=None):
        if not self.channel: return
        
        if text_data:
            if text_data.startswith('{"type":"resize"'):
                msg = json.loads(text_data)
                self.channel.resize_pty(width=msg["cols"], height=msg["rows"])
            else:
                self.channel.send(text_data)

    async def disconnect(self, close_code):
        self.running = False
        if self.ssh: self.ssh.close()