from django.urls import re_path

from .consumers import CyberLabConsumer


websocket_urlpatterns = [

    re_path(

        r'ws/cyber/(?P<session_id>\w+)/$',

        CyberLabConsumer.as_asgi()
    ),
]