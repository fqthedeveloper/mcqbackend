# views.py (Backend - Django)
import json
import logging
import asyncio
import os
import platform
import docker
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import PracticalExamSession
from django.conf import settings
import time
import threading
import select
import urllib.parse
import struct

logger = logging.getLogger(__name__)

class PracticalTerminalConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.container = None
        self.attach_socket = None
        self.socket_active = True
        self.last_pong = None
        self.read_thread = None
        self.read_thread_running = True
        self.output_queue = asyncio.Queue()
        self.session_id = None
        self.token = None
        self.forward_task = None
        self.ping_task = None
        self.main_loop = None
        self.initialized = False

    # Class-level Docker client with lazy initialization
    _docker_client = None
    _docker_lock = threading.Lock()

    @classmethod
    def get_docker_client(cls):
        with cls._docker_lock:
            if cls._docker_client is None:
                try:
                    if platform.system() == 'Windows':
                        cls._docker_client = docker.DockerClient(
                            base_url='tcp://localhost:2375',
                            timeout=300
                        )
                    else:
                        cls._docker_client = docker.DockerClient(
                            base_url='unix://var/run/docker.sock',
                            timeout=300
                        )
                    cls._docker_client.ping()
                    logger.info("✅ Docker client connected successfully")
                except Exception as e:
                    logger.error(f"❌ Docker connection failed: {str(e)}")
                    raise RuntimeError("Docker daemon not available")
            return cls._docker_client

    def get_token_from_query(self):
        """Extract session token from query string"""
        query_string = self.scope.get('query_string', b'').decode()
        query_params = urllib.parse.parse_qs(query_string)
        return query_params.get('session_token', [None])[0]

    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.token = self.get_token_from_query()
        self.main_loop = asyncio.get_running_loop()
        
        if not self.token:
            await self.close(code=4001)
            return
            
        try:
            session = await self.get_session()
            if not session:
                await self.close(code=4003)
                return

            client = self.get_docker_client()
            self.container = await self.get_or_create_container(client, session)
            
            # Create an exec instance for interactive shell
            exec_id = client.api.exec_create(
                self.container.id,
                "/bin/bash",  # Using bash shell
                tty=True,
                stdin=True,
                stdout=True,
                stderr=True,
                environment={"TERM": "xterm-256color"}
            )['Id']
            
            # Start the exec instance with a socket
            self.exec_socket = client.api.exec_start(
                exec_id,
                socket=True,
                tty=True
            )
            
            # Get the raw socket
            socket = self.exec_socket._sock
            
            # Set non-blocking mode
            socket.setblocking(False)
            
            await self.accept()
            self.last_pong = time.time()
            
            # Start output reader thread
            self.read_thread_running = True
            self.read_thread = threading.Thread(
                target=self.read_socket_output_thread,
                args=(socket,),
                daemon=True
            )
            self.read_thread.start()
            
            # Start output forwarding task
            self.forward_task = asyncio.create_task(self.forward_output())
            
            # Start ping task
            self.ping_task = asyncio.create_task(self.send_pings())
            
            # Send initial resize to set terminal dimensions
            await self.send_resize_command(80, 24)
            
            # Send welcome message
            welcome_msg = "\r\n🚀 Connected to exam environment. Start working on your tasks...\r\n"
            await self.send(bytes_data=welcome_msg.encode('utf-8'))
            
            # Send a newline to trigger the prompt
            socket.sendall(b"\r\n")
            
            self.initialized = True
            
        except docker.errors.NotFound:
            logger.error(f"Container not found for session {self.session_id}")
            await self.send_error('❌ Container not found. Please restart the exam.')
            await self.close(code=4002)
        except Exception as e:
            logger.exception(f"Connection error: {str(e)}")
            await self.send_error(f'❌ Connection failed: {str(e)}')
            await self.close(code=4003)

    def read_socket_output_thread(self, socket):
        """Thread to read socket output and put into async queue"""
        while self.read_thread_running:
            try:
                # Use select to check for readable socket
                rlist, _, _ = select.select([socket], [], [], 0.5)
                if rlist:
                    # Read raw byte stream
                    data = socket.recv(4096)
                    if data:
                        # Put data in queue using thread-safe method
                        asyncio.run_coroutine_threadsafe(
                            self.output_queue.put(data),
                            self.main_loop
                        )
                    else:
                        # Empty data indicates socket closed
                        logger.info("Docker socket closed remotely")
                        self.read_thread_running = False
                # Handle thread shutdown
                elif not self.read_thread_running:
                    break
            except (BlockingIOError, select.error):
                pass
            except Exception as e:
                if self.read_thread_running:
                    logger.error(f"Socket read error: {str(e)}")
                    asyncio.run_coroutine_threadsafe(
                        self.send_error('❌ Terminal connection lost'),
                        self.main_loop
                    )
                break

    async def forward_output(self):
        """Forward queued output to WebSocket"""
        while self.socket_active:
            try:
                data = await asyncio.wait_for(
                    self.output_queue.get(), 
                    timeout=1.0
                )
                # Send as binary data
                await self.send(bytes_data=data)
            except asyncio.TimeoutError:
                # Check if we should exit
                if not self.socket_active:
                    break
            except Exception as e:
                if self.socket_active:
                    logger.error(f"Output forwarding error: {str(e)}")
                    break

    async def send_pings(self):
        """Periodically send ping messages to keep connection alive"""
        while self.socket_active:
            try:
                # Send WebSocket ping
                await self.send(text_data=json.dumps({
                    'type': 'ping',
                    'timestamp': time.time()
                }))
                
                # Check if we haven't received a pong recently
                if time.time() - self.last_pong > 60:
                    logger.warning("No pong response in 60 seconds, closing connection")
                    await self.close(code=4006)
                    return
                    
                # Wait before next ping
                await asyncio.sleep(20)
            except asyncio.CancelledError:
                return
            except Exception as e:
                if self.socket_active:
                    logger.error(f"Ping error: {str(e)}")
                    await self.close(code=4007)
                return

    async def send_resize_command(self, cols, rows):
        """Resize the container TTY"""
        if hasattr(self, 'exec_socket') and self.exec_socket:
            resize_package = struct.pack('!BHH', 1, rows, cols)
            try:
                self.exec_socket._sock.sendall(resize_package)
            except Exception as e:
                logger.error(f"Error sending resize command: {str(e)}")

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
                logger.warning("Container not found, creating new one")
                return await self.create_new_container(client, session)
        else:
            logger.info("Creating new container")
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
        # Create volume path
        volume_path = os.path.join(settings.BASE_DIR, 'exam_data', str(session.id))
        os.makedirs(volume_path, exist_ok=True)
        
        # Windows path conversion
        if platform.system() == 'Windows':
            volume_path = volume_path.replace('\\', '/').replace(':', '')
            volume_path = f'/{volume_path}'
        
        # Special configuration for Red Hat UBI images
        volumes = {
            volume_path: {'bind': '/exam', 'mode': 'rw'}
        }
        cap_add = []
        security_opt = []
        command = "sleep infinity"
        
        # Add systemd support for RHEL-based images
        if "redhat" in session.exam.docker_image.lower():
            volumes['/sys/fs/cgroup'] = {'bind': '/sys/fs/cgroup', 'mode': 'ro'}
            cap_add.append('SYS_ADMIN')
            security_opt = ['seccomp=unconfined']
            command = "/usr/sbin/init"
            logger.info("Configuring container for systemd support")
        
        # Create container
        container = client.containers.run(
            session.exam.docker_image,
            command=command,
            detach=True,
            tty=True,
            stdin_open=True,
            environment={
                **session.exam.environment_vars,
                "STUDENT_ID": str(session.student.id),
                "EXAM_ID": str(session.exam.id),
                "container": "docker",  # Fix for systemd in containers
                "TERM": "xterm-256color"
            },
            volumes=volumes,
            name=f"practical-exam-{session.id}",
            cap_add=cap_add,
            security_opt=security_opt,
            privileged=True  # Required for systemd
        )
        
        # Wait for container to start
        for _ in range(20):  # Increased timeout for systemd containers
            container.reload()
            if container.status == 'running':
                # Additional wait for systemd to initialize
                time.sleep(3)
                break
            time.sleep(1)
        else:
            raise RuntimeError("Container failed to start")
        
        # Run setup command if exists
        if session.exam.setup_command:
            # Special handling for RHEL-based images
            if "redhat" in session.exam.docker_image.lower():
                # Wait for systemd to initialize
                time.sleep(5)
            
            exit_code, output = container.exec_run(
                session.exam.setup_command,
                workdir="/exam",
                tty=True
            )
            logger.info(f"Setup command executed with code: {exit_code}")
        
        # Update session
        session.container_id = container.id
        session.save()
        return container

    async def disconnect(self, close_code):
        """Clean up resources on disconnect"""
        self.socket_active = False
        self.read_thread_running = False
        
        # Stop all background tasks
        if self.ping_task:
            self.ping_task.cancel()
        if self.forward_task:
            self.forward_task.cancel()
        
        # Close Docker socket
        if hasattr(self, 'exec_socket') and self.exec_socket:
            try:
                self.exec_socket.close()
            except Exception as e:
                logger.error(f"Error closing socket: {str(e)}")
        
        # Wait for reader thread to exit
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=2.0)
        
        logger.info(f"Disconnected from terminal session: {self.session_id}")

    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming WebSocket messages"""
        if not hasattr(self, 'exec_socket') or not self.initialized:
            return
            
        # Handle pong response
        if text_data and text_data.startswith('{"type":"pong"'):
            try:
                data = json.loads(text_data)
                self.last_pong = time.time()
                return
            except:
                pass

        # Handle resize command
        if text_data and text_data.startswith('{"type":"resize"'):
            try:
                data = json.loads(text_data)
                # Resize container TTY
                await self.send_resize_command(
                    data.get('cols', 80),
                    data.get('rows', 24)
                )
                return
            except Exception as e:
                logger.error(f"Resize error: {str(e)}")
                return

        # Handle regular input
        try:
            if text_data:
                # Send input to container
                self.exec_socket._sock.sendall(text_data.encode('utf-8'))
            elif bytes_data:
                # Send binary data to container
                self.exec_socket._sock.sendall(bytes_data)
        except Exception as e:
            logger.error(f"Send error: {str(e)}")
            await self.send_error('❌ Failed to send input to terminal')
            await self.close(code=4005)

    async def send_error(self, message):
        """Send error message to client"""
        if self.socket_active:
            # Send error as bytes to ensure proper terminal display
            await self.send(bytes_data=f"\r\n\x1b[31m{message}\x1b[0m\r\n".encode('utf-8'))