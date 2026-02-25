import asyncio
import json
import paramiko
import time
import socket
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.db import close_old_connections


class SSHConsumer(AsyncWebsocketConsumer):

    # ======================================================
    # CONNECT
    # ======================================================
    async def connect(self):
        from .models import PracticalSession

        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        await self.accept()

        self.running = False
        self.ssh = None
        self.channel = None
        self.keepalive_task = None
        self.reader_task = None

        try:
            close_old_connections()

            self.session = await asyncio.to_thread(
                PracticalSession.objects.select_related("task").get,
                pk=self.session_id
            )

            if not self.session.vm_ip or self.session.status != "running":
                await self.send(
                    text_data="\r\n[Session not active or VM not ready]\r\n"
                )
                await self.close()
                return

            self.running = True

            await asyncio.to_thread(self.start_ssh_transport)

            self.reader_task = asyncio.create_task(self.read_ssh())
            self.keepalive_task = asyncio.create_task(self.keepalive())

        except Exception as e:
            await self.send(
                text_data=f"\r\n[Connection Error: {str(e)}]\r\n"
            )
            await self.close()

    # ======================================================
    # SSH CONNECT WITH RETRY + KEEPALIVE
    # ======================================================
    def start_ssh_transport(self):

        max_attempts = 15
        attempt = 0

        while attempt < max_attempts:
            try:
                self.ssh = paramiko.SSHClient()
                self.ssh.set_missing_host_key_policy(
                    paramiko.AutoAddPolicy()
                )

                self.ssh.connect(
                    hostname=self.session.vm_ip,
                    username=settings.VM_USER,
                    password=settings.VM_PASSWORD,
                    look_for_keys=False,
                    allow_agent=False,
                    timeout=30,
                    banner_timeout=30,
                    auth_timeout=30,
                )

                transport = self.ssh.get_transport()

                # 🔥 VERY IMPORTANT
                transport.set_keepalive(20)

                self.channel = self.ssh.invoke_shell(
                    term="xterm-256color",
                    width=120,
                    height=40
                )

                self.channel.settimeout(0.0)
                self.channel.setblocking(False)

                time.sleep(1)

                self.channel.send("clear\n")
                self.channel.send("echo '=== EXAM TERMINAL CONNECTED ==='\n")
                self.channel.send("clear\n")

                return

            except Exception as e:
                attempt += 1
                print(f"[SSH Attempt {attempt}] Failed: {e}")
                time.sleep(2)

        raise Exception("SSH connection failed after retries")

    # ======================================================
    # KEEPALIVE LOOP
    # ======================================================
    async def keepalive(self):

        while self.running:
            try:
                if self.ssh:
                    transport = self.ssh.get_transport()
                    if transport and transport.is_active():
                        transport.send_ignore()
                await asyncio.sleep(15)
            except:
                await asyncio.sleep(15)

    # ======================================================
    # READ FROM SSH (HIGH OUTPUT SAFE)
    # ======================================================
    async def read_ssh(self):

        while self.running:
            try:
                if not self.channel:
                    break

                if self.channel.recv_ready():

                    data = await asyncio.to_thread(
                        self.channel.recv,
                        32768
                    )

                    if data:
                        await self.send(
                            text_data=data.decode("utf-8", "replace")
                        )

                if self.channel.closed:
                    self.running = False
                    break

                await asyncio.sleep(0.005)

            except socket.timeout:
                continue

            except Exception as e:
                print("Read Error:", e)
                await asyncio.sleep(0.1)

    # ======================================================
    # RECEIVE FROM BROWSER
    # ======================================================
    async def receive(self, text_data=None, bytes_data=None):

        if not self.channel:
            return

        try:
            if text_data and text_data.startswith('{"type":"resize"'):
                msg = json.loads(text_data)
                cols = msg.get("cols")
                rows = msg.get("rows")

                if isinstance(cols, int) and isinstance(rows, int):
                    await asyncio.to_thread(
                        self.channel.resize_pty,
                        width=cols,
                        height=rows
                    )
                return

            if text_data:
                await asyncio.to_thread(
                    self.channel.send,
                    text_data
                )

        except Exception as e:
            print("Receive Error:", e)

    # ======================================================
    # DISCONNECT CLEANLY
    # ======================================================
    async def disconnect(self, close_code):

        self.running = False

        if self.reader_task:
            self.reader_task.cancel()

        if self.keepalive_task:
            self.keepalive_task.cancel()

        if self.channel:
            try:
                self.channel.close()
            except:
                pass

        if self.ssh:
            try:
                self.ssh.close()
            except:
                pass