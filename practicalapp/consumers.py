import asyncio
import json
import paramiko
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import  settings


class SSHConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        from .models import PracticalSession

        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        await self.accept()

        try:
            self.session = await asyncio.to_thread(
                PracticalSession.objects.get,
                pk=self.session_id
            )

            self.running = True
            self.ssh = None
            self.channel = None

            await asyncio.to_thread(self.start_ssh_transport)
            asyncio.create_task(self.read_ssh())

        except Exception as e:
            await self.send(text_data=f"\r\n[Internal Error: {str(e)}]\r\n")
            await self.close()

    # ======================================================
    # DIRECT SSH LOGIN AS kiosk USER
    # ======================================================
    def start_ssh_transport(self):

        max_attempts = 10
        attempt = 0

        while attempt < max_attempts:
            try:
                self.ssh = paramiko.SSHClient()
                self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                # 🔥 CONNECT DIRECTLY AS kiosk
                self.ssh.connect(
                    hostname=self.session.vm_ip,
                    username=settings.VM_USER,
                    password=settings.VM_PASSWORD,
                    look_for_keys=False,
                    allow_agent=False,
                    timeout=20,
                    banner_timeout=30,
                    auth_timeout=30,
                )

                self.channel = self.ssh.invoke_shell(
                    term="xterm-256color",
                    width=120,
                    height=40
                )

                self.channel.setblocking(0)

                # Clean exam terminal banner
                time.sleep(1)
                self.channel.send("clear\n")
                self.channel.send("      EXAM TERMINAL CONNECTED       '\n")

                return

            except Exception as e:
                attempt += 1
                print(f"SSH attempt {attempt} failed: {e}")
                time.sleep(3)

        raise Exception("SSH connection failed after multiple attempts")

    # ======================================================
    # READ SSH OUTPUT
    # ======================================================
    async def read_ssh(self):
        while self.running:
            try:
                if self.channel and self.channel.recv_ready():
                    data = await asyncio.to_thread(
                        self.channel.recv,
                        8192
                    )

                    if data:
                        await self.send(
                            text_data=data.decode("utf-8", "replace")
                        )

                if self.channel and self.channel.closed:
                    self.running = False
                    await self.close()

                await asyncio.sleep(0.01)

            except Exception as e:
                print("Read Error:", e)
                await asyncio.sleep(0.1)

    # ======================================================
    # SEND INPUT TO SSH
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
            else:
                if text_data:
                    await asyncio.to_thread(
                        self.channel.send,
                        text_data
                    )

        except Exception as e:
            print("Receive Error:", e)

    # ======================================================
    # CLEAN DISCONNECT
    # ======================================================
    async def disconnect(self, close_code):
        self.running = False

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
