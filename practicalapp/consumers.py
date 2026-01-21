import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer

USE_MOCK_VM = True   # 🔥 Windows safe

class TerminalConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        await self.accept()

        await self.send(json.dumps({
            "type": "output",
            "data": "Connected to exam terminal\r\n"
        }))

    async def receive(self, text_data):
        data = text_data

        if USE_MOCK_VM:
            # Fake shell
            await asyncio.sleep(0.2)
            await self.send(json.dumps({
                "type": "output",
                "data": f"$ {data}\r\ncommand executed\r\n"
            }))

    async def disconnect(self, close_code):
        pass
