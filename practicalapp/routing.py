from django.urls import re_path
from .consumers import SSHConsumer

websocket_urlpatterns = [
    re_path(
        r"ws/practical/terminal/(?P<session_id>\d+)/$",
        SSHConsumer.as_asgi(),
    ),
]
