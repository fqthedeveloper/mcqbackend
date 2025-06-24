import asyncio
import json
import threading
import docker
from channels.generic.websocket import AsyncWebsocketConsumer

class PracticalTerminalConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.container_id = self.scope['url_route']['kwargs']['container_id']
        self.user = self.scope["user"]
        
        # Verify user has access to this container
        if not self.user.is_authenticated:
            await self.close()
            return
            
        # Verify container belongs to user's active session
        if not self.user.practicalexamsession_set.filter(
            container_id=self.container_id,
            status='running'
        ).exists():
            await self.close()
            return
        
        await self.accept()
        
        # Create Docker exec instance
        client = docker.from_env()
        container = client.containers.get(self.container_id)
        self.exec_instance = container.exec_run(
            "bash",
            stdin=True,
            socket=True,
            tty=True,
            privileged=True
        )
        
        # Start thread to forward container output to websocket
        self.thread = threading.Thread(target=self.forward_output)
        self.thread.daemon = True
        self.thread.start()

    async def disconnect(self, close_code):
        if hasattr(self, 'exec_instance'):
            # Close the exec instance
            self.exec_instance.output.close()

    def forward_output(self):
        while True:
            try:
                data = self.exec_instance.output.read(1024)
                if not data:
                    break
                asyncio.run(self.send(text_data=data.decode()))
            except:
                break

    async def receive(self, text_data):
        # Forward user input to container
        if hasattr(self, 'exec_instance'):
            self.exec_instance.output.write(text_data.encode())