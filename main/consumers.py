import json
import logging
import asyncio
import os
import platform
import select
import docker
import time
import threading
import socket
import urllib.parse
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import PracticalExamSession
from django.conf import settings

logger = logging.getLogger(__name__)

class PracticalTerminalConsumer(AsyncWebsocketConsumer):
    _docker_client = None
    _docker_lock = threading.Lock()

    @classmethod
    def get_docker_client(cls):
        with cls._docker_lock:
            if cls._docker_client is None:
                try:
                    cls._docker_client = docker.from_env(timeout=300)
                    cls._docker_client.ping()
                except Exception as e:
                    logger.error(f"Docker connection failed: {str(e)}")
                    raise RuntimeError("Docker daemon not available")
            return cls._docker_client

    def get_token_from_query(self):
        query_string = self.scope.get('query_string', b'').decode()
        query_params = urllib.parse.parse_qs(query_string)
        return query_params.get('token', [None])[0] or query_params.get('session_token', [None])[0]

    async def connect(self):
        # Initialize attributes first
        self.ping_task = None
        self.read_thread = None
        self.exec_socket = None
        self.socket = None
        self.output_queue = None
        self.socket_active = False
        self.read_thread_running = False
        self.last_pong = time.time()
        self.exec_id = None
        
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.token = self.get_token_from_query()
        
        if not self.token:
            logger.error(f"No token provided for session {self.session_id}")
            await self.close(code=4001)
            return
            
        try:
            session = await self.get_session()
            if not session:
                logger.error(f"Invalid session or token for session {self.session_id}")
                await self.close(code=4003)
                return

            client = self.get_docker_client()
            self.container = await self.get_or_create_container(client, session)
            
            # Create an exec instance for interactive shell
            self.exec_id = client.api.exec_create(
                self.container.id,
                "/bin/bash",
                tty=True,
                stdin=True,
                stdout=True,
                stderr=True,
                environment={"TERM": "xterm-256color"}
            )['Id']
            
            # Start the exec instance with a socket
            self.exec_socket = client.api.exec_start(
                self.exec_id,
                socket=True,
                tty=True
            )
            
            # Handle socket differences between Windows and Unix
            if platform.system() == 'Windows':
                # Windows uses NpipeSocket
                self.socket = self.exec_socket
            else:
                # Unix uses regular sockets
                self.socket = self.exec_socket._sock
                # Set non-blocking mode only for Unix
                self.socket.setblocking(False)
                # Unix-specific socket flags (using try-except for safety)
                try:
                    import fcntl
                    flags = fcntl.fcntl(self.socket, fcntl.F_GETFD)
                    fcntl.fcntl(self.socket, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)
                except ImportError:
                    # fcntl not available on Windows
                    pass
                except Exception as e:
                    logger.warning(f"Could not set socket flags: {str(e)}")
            
            # Initialize output handling
            self.output_queue = asyncio.Queue()
            self.main_loop = asyncio.get_running_loop()
            self.socket_active = True
            
            await self.accept()
            
            # Start output reader thread
            self.read_thread_running = True
            self.read_thread = threading.Thread(
                target=self.read_socket_output,
                daemon=True
            )
            self.read_thread.start()
            
            # Start ping task
            self.ping_task = asyncio.create_task(self.send_pings())
            
            # Send welcome message
            welcome_msg = "\r\n🚀 Connected to exam environment. Start working on your tasks...\r\n"
            await self.send(text_data=welcome_msg)
            
            # Send initial resize command
            await self.send_resize_command(80, 24)
            
            # Send newline to trigger prompt
            if platform.system() == 'Windows':
                self.exec_socket.send(b"\r\n")
            else:
                self.socket.sendall(b"\r\n")
            
        except docker.errors.NotFound:
            logger.error(f"Container not found for session {self.session_id}")
            await self.send(text_data='\r\n❌ Container not found. Please restart the exam.\r\n')
            await self.close(code=4002)
        except Exception as e:
            logger.exception(f"Connection error: {str(e)}")
            await self.send(text_data=f'\r\n❌ Connection failed: {str(e)}\r\n')
            await self.close(code=4003)
    
    def read_socket_output(self):
        while self.read_thread_running and self.socket_active:
            try:
                if platform.system() == 'Windows':
                    # Windows: use simple recv without select
                    try:
                        data = self.exec_socket.recv(4096)
                        if data:
                            asyncio.run_coroutine_threadsafe(
                                self.send(bytes_data=data),
                                self.main_loop
                            )
                    except BlockingIOError:
                        time.sleep(0.1)
                    except Exception as e:
                        logger.error(f"Windows socket read error: {str(e)}")
                        self.socket_active = False
                else:
                    # Unix: use select for non-blocking I/O
                    rlist, _, _ = select.select([self.socket], [], [], 0.5)
                    if rlist:
                        data = self.socket.recv(4096)
                        if data:
                            asyncio.run_coroutine_threadsafe(
                                self.send(bytes_data=data),
                                self.main_loop
                            )
            except Exception as e:
                if self.read_thread_running:
                    logger.error(f"Socket read error: {str(e)}")
                self.read_thread_running = False

    async def send_pings(self):
        try:
            while self.socket_active:
                # Send ping as JSON text
                await self.send(text_data=json.dumps({
                    'type': 'ping',
                    'timestamp': time.time()
                }))
                
                # Wait for pong response
                await asyncio.sleep(20)  # Increased to 20 seconds
                
                # Check if we got a pong response
                if time.time() - self.last_pong > 60:  # Increased to 60 seconds
                    logger.warning("No pong response in 60 seconds. Closing connection.")
                    await self.close(code=4006)
                    return
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Ping task error: {str(e)}")

    async def send_resize_command(self, cols, rows):
        if self.exec_id:
            try:
                client = self.get_docker_client()
                # Use Docker API to resize the terminal properly
                client.api.exec_resize(self.exec_id, height=rows, width=cols)
                logger.debug(f"Terminal resized to {cols}x{rows}")
            except Exception as e:
                logger.error(f"Resize command failed: {str(e)}")

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
        if session.container_id:
            try:
                container = client.containers.get(session.container_id)
                if container.status != 'running':
                    container.start()
                    await self.wait_for_container(container)
                return container
            except docker.errors.NotFound:
                return await self.create_new_container(client, session)
        else:
            return await self.create_new_container(client, session)

    async def wait_for_container(self, container, max_retries=10, delay=1):
        for _ in range(max_retries):
            container.reload()
            if container.status == 'running':
                return
            await asyncio.sleep(delay)
        raise RuntimeError("Container failed to start")

    @database_sync_to_async
    def create_new_container(self, client, session):
        volume_path = os.path.join(settings.BASE_DIR, 'exam_data', str(session.id))
        os.makedirs(volume_path, exist_ok=True)
        
        # Handle Windows path conversion
        if platform.system() == 'Windows':
            volume_path = volume_path.replace('\\', '/').replace(':', '')
            volume_path = f'/{volume_path}'
        
        volumes = {
            volume_path: {'bind': '/exam', 'mode': 'rw'}
        }
        
        # Run container with bash shell
        container = client.containers.run(
            session.exam.docker_image,
            command="/bin/bash",
            detach=True,
            tty=True,
            stdin_open=True,
            environment={
                "TERM": "xterm-256color"
            },
            volumes=volumes,
            name=f"practical-exam-{session.id}",
        )
        
        # Wait for container to start
        for _ in range(20):
            container.reload()
            if container.status == 'running':
                time.sleep(2)  # Additional buffer time
                break
            time.sleep(1)
        else:
            raise RuntimeError("Container failed to start")
        
        # Save container ID to session
        session.container_id = container.id
        session.save()
        return container

    async def disconnect(self, close_code):
        self.socket_active = False
        self.read_thread_running = False
        
        # Safely handle ping_task attribute
        if hasattr(self, 'ping_task') and self.ping_task:
            self.ping_task.cancel()
            try:
                await self.ping_task
            except asyncio.CancelledError:
                pass
        
        if hasattr(self, 'exec_socket') and self.exec_socket:
            try:
                if platform.system() == 'Windows':
                    self.exec_socket.close()
                else:
                    self.socket.close()
            except Exception:
                pass
        
        if hasattr(self, 'read_thread') and self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=1.0)

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data:
            # Binary data from terminal (user input)
            try:
                if hasattr(self, 'socket') and self.socket_active:
                    if platform.system() == 'Windows':
                        self.exec_socket.send(bytes_data)
                    else:
                        self.socket.sendall(bytes_data)
            except Exception as e:
                logger.error(f"Receive bytes error: {str(e)}")
                await self.close(code=4005)

        elif text_data:
            try:
                # Handle pong messages
                if text_data.startswith('{"type":"pong"'):
                    data = json.loads(text_data)
                    self.last_pong = time.time()
                    logger.debug("Received pong response")
                    return

                # Handle resize commands
                if text_data.startswith('{"type":"resize"'):
                    data = json.loads(text_data)
                    await self.send_resize_command(
                        data.get('cols', 80),
                        data.get('rows', 24)
                    )
                    return
            
            except json.JSONDecodeError:
                # It's normal terminal input, forward it as bytes
                try:
                    if hasattr(self, 'socket') and self.socket_active:
                        input_bytes = text_data.encode('utf-8')
                        if platform.system() == 'Windows':
                            self.exec_socket.send(input_bytes)
                        else:
                            self.socket.sendall(input_bytes)
                except Exception as e:
                    logger.error(f"Text input handling failed: {str(e)}")
                    await self.close(code=4005)

            except Exception as e:
                logger.error(f"Receive text error: {str(e)}")