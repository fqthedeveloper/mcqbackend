from channels.generic.websocket import AsyncJsonWebsocketConsumer


class CyberLabConsumer(
    AsyncJsonWebsocketConsumer
):

    async def connect(self):

        self.session_id = self.scope[
            'url_route'
        ]['kwargs']['session_id']

        self.room_group_name = (
            f'cyber_{self.session_id}'
        )

        await self.channel_layer.group_add(

            self.room_group_name,

            self.channel_name
        )

        await self.accept()

        await self.send_json({

            "type": "connected",

            "message": "Cyber websocket connected",

            "session_id": self.session_id,
        })

    async def disconnect(
        self,
        close_code
    ):

        await self.channel_layer.group_discard(

            self.room_group_name,

            self.channel_name
        )

    async def receive_json(
        self,
        content
    ):

        await self.channel_layer.group_send(

            self.room_group_name,

            {

                "type": "broadcast_message",

                "data": content
            }
        )

    async def broadcast_message(
        self,
        event
    ):

        await self.send_json(
            event["data"]
        )

    async def vm_update(
        self,
        event
    ):

        await self.send_json({

            "type": "vm_update",

            "data": event["data"]
        })

    async def exam_update(
        self,
        event
    ):

        await self.send_json({

            "type": "exam_update",

            "data": event["data"]
        })