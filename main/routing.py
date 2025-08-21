from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/practical/(?P<session_id>\w+)/$', consumers.PracticalTerminalConsumer.as_asgi()),
]