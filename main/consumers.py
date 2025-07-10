import json
import logging
import asyncio
import os
import platform
import select
import threading
import time
import urllib.parse

import docker
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings

from .models import PracticalExamSession

logger = logging.getLogger(__name__)

class PracticalTerminalConsumer(AsyncWebsocketConsumer):
    _docker_client = None
    _docker_lock = threading.Lock()

    @classmethod
    def get_docker_client(cls):
        with cls._docker_lock:
            if cls._docker_client is None:
                cls._docker_client = docker.from_env(timeout=300)
                cls._docker_client.ping()
            return cls._docker_client

    def get_token_from_query(self):
        qs = self.scope.get('query_string', b'').decode()
        params = urllib.parse.parse_qs(qs)
        return params.get('token', [None])[0]

    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.token = self.get_token_from_query()
        if not self.token:
            return await self.close(code=4001)

        session = await self.get_session()
        if not session:
            return await self.close(code=4003)

        client = self.get_docker_client()
        self.container = await self.get_or_create_container(client, session)

        # Create interactive bash exec
        exec_cfg = client.api.exec_create(
            self.container.id,
            cmd="/bin/bash",
            tty=True,
            stdin=True,
            stdout=True,
            stderr=True,
            environment={"TERM": "xterm-256color"}
        )
        self.exec_id = exec_cfg['Id']

        # Start it and grab a socket
        sock = client.api.exec_start(self.exec_id, tty=True, socket=True)
        if platform.system().lower().startswith('win'):
            self.sock = sock
        else:
            self.sock = sock._sock
            self.sock.setblocking(False)

        # Bookkeeping
        self.queue = asyncio.Queue()
        self.socket_active = True
        self.loop = asyncio.get_running_loop()

        # Spawn reader thread
        self.read_thread = threading.Thread(
            target=self._reader_thread,
            daemon=True
        )
        self.read_thread.start()

        # Spawn sender task
        self.sender_task = asyncio.create_task(self._sender())

        await self.accept()

        # Send initial prompt
        self.sock.sendall(b"\r\n")

    async def _sender(self):
        while self.socket_active:
            data = await self.queue.get()
            if data is None:
                break
            await self.send(bytes_data=data)

    def _reader_thread(self):
        while self.socket_active:
            try:
                if platform.system().lower().startswith('win'):
                    chunk = self.sock.recv(4096)
                else:
                    rlist, _, _ = select.select([self.sock], [], [], 0.5)
                    if not rlist:
                        continue
                    chunk = self.sock.recv(4096)
                if not chunk:
                    break
                asyncio.run_coroutine_threadsafe(self.queue.put(chunk), self.loop)
            except Exception:
                time.sleep(0.1)

    async def receive(self, text_data=None, bytes_data=None):
        if not self.socket_active:
            return

        payload = bytes_data if bytes_data is not None else text_data.encode()
        try:
            self.sock.sendall(payload)
        except Exception as e:
            logger.error(f"Send error: {e}")
            await self.close(code=4005)

    async def disconnect(self, code):
        self.socket_active = False
        # tell the sender to exit
        await self.queue.put(None)
        if hasattr(self, 'sender_task'):
            self.sender_task.cancel()
        if hasattr(self, 'sock'):
            try: self.sock.close()
            except: pass
        if hasattr(self, 'read_thread') and self.read_thread.is_alive():
            self.read_thread.join(timeout=1)

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

    async def get_or_create_container(self, client, session):
        # If already created, start/reload; otherwise create new
        if session.container_id:
            try:
                c = client.containers.get(session.container_id)
                if c.status != 'running':
                    c.start()
                return c
            except docker.errors.NotFound:
                pass

        # Create fresh
        volume = os.path.join(settings.BASE_DIR, 'exam_data', str(session.id))
        os.makedirs(volume, exist_ok=True)
        if platform.system().lower().startswith('win'):
            volume = volume.replace('\\', '/').replace(':', '')

        container = client.containers.run(
            session.exam.docker_image,
            command="/usr/sbin/init",
            detach=True,
            tty=True,
            stdin_open=True,
            privileged=True,
            volumes={volume: {'bind': '/root', 'mode': 'rw'}},
            name=f"practical-exam-{session.id}"
        )
        # wait until healthy/running
        for _ in range(20):
            container.reload()
            if container.status == 'running':
                break
            await asyncio.sleep(1)

        session.container_id = container.id
        session.save()
        return container
