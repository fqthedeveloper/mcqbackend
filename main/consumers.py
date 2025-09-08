# consumers.py
import asyncio
import threading
import time
import logging
import urllib.parse
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import paramiko
import socket

from .models import PracticalExamSession

logger = logging.getLogger(__name__)


class PracticalTerminalConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """
        Handles new WebSocket connection
        """
        self.session_id = self.scope['url_route']['kwargs'].get('session_id')
        qs = self.scope.get('query_string', b'').decode()
        token = urllib.parse.parse_qs(qs).get('token', [None])[0]

        if not token:
            await self.close(code=4001)  # No token provided
            return

        # Fetch session
        self.session = await self.get_session(self.session_id, token)
        if not self.session:
            await self.close(code=4003)  # Invalid or expired session
            return

        # Check if session is running and VM is available
        if self.session.status != 'running' or not self.session.ssh_port:
            await self.close(code=4005)  # VM not available
            return

        # Store VM connection details
        self.port = self.session.ssh_port
        self.username = self.session.exam.vm_username
        self.password = self.session.exam.vm_password

        # SSH connection placeholders
        self.ssh_client = None
        self.ssh_chan = None
        self._running = False
        self.loop = asyncio.get_event_loop()

        # Attempt SSH connection in executor
        try:
            self.ssh_client, self.ssh_chan = await self.loop.run_in_executor(
                None, self._blocking_ssh_connect, self.port, self.username, self.password
            )
        except Exception as e:
            logger.error("SSH connect failed: %s", e)
            await self.close(code=4006)
            return

        self._running = True

        # Start reader thread
        self.reader_thread = threading.Thread(
            target=self._read_ssh_output, daemon=True
        )
        self.reader_thread.start()

        # Accept WebSocket connection
        await self.accept()

    async def disconnect(self, close_code):
        """
        Cleanup when client disconnects
        """
        self._running = False
        if getattr(self, 'ssh_chan', None):
            try:
                self.ssh_chan.close()
            except Exception:
                pass
        if getattr(self, 'ssh_client', None):
            try:
                self.ssh_client.close()
            except Exception:
                pass

    async def receive(self, text_data=None, bytes_data=None):
        """
        Handle input from WebSocket -> send to SSH
        """
        if text_data and getattr(self, 'ssh_chan', None) and self.ssh_chan.active:
            try:
                await self.loop.run_in_executor(
                    None, self.ssh_chan.send, text_data.encode("utf-8")
                )
            except Exception as e:
                logger.error("Error sending to SSH channel: %s", e)
                await self.close()

    def _blocking_ssh_connect(self, port, username, password):
        """
        Blocking SSH connection method to be run in a thread
        """
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        max_retries = 3
        for attempt in range(max_retries):
            try:
                client.connect(
                    "127.0.0.1",
                    port=int(port),
                    username=username,
                    password=password,
                    timeout=15,
                    banner_timeout=30,
                )
                chan = client.invoke_shell(term="xterm-256color")
                chan.settimeout(0.5)
                return client, chan
            except (socket.timeout, paramiko.ssh_exception.SSHException):
                if attempt == max_retries - 1:
                    raise
                time.sleep(2)  # retry
            except Exception:
                raise

    def _read_ssh_output(self):
        """
        Continuously read SSH output and send to WebSocket
        """
        while self._running and self.ssh_chan:
            try:
                if self.ssh_chan.recv_ready():
                    data = self.ssh_chan.recv(4096)
                    if data:
                        asyncio.run_coroutine_threadsafe(
                            self.send(bytes_data=data), self.loop
                        )
                else:
                    time.sleep(0.01)
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error("SSH read error: %s", e)
                break

    @database_sync_to_async
    def get_session(self, session_id, token):
        """
        Fetch session safely from DB
        """
        try:
            return PracticalExamSession.objects.select_related("exam").get(
                id=session_id, token=token
            )
        except PracticalExamSession.DoesNotExist:
            return None