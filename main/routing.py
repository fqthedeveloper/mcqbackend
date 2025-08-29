from django.urls import re_path
from .consumers import PracticalTerminalConsumer

websocket_urlpatterns = [
    re_path(r'ws/practical/(?P<session_id>\d+)/$', PracticalTerminalConsumer.as_asgi()),
]