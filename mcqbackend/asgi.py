import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import re_path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcqbackend.settings')

# Initialize Django BEFORE importing models
django.setup()

# Now safely import consumers
from main import consumers

# Define WebSocket URL patterns
websocket_urlpatterns = [
    re_path(r'^ws/practical/(?P<session_id>\d+)/$', consumers.PracticalTerminalConsumer.as_asgi()),
]

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})