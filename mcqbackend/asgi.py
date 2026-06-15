import os

from django.core.asgi import get_asgi_application

from channels.routing import (
    ProtocolTypeRouter,
    URLRouter
)

from channels.auth import AuthMiddlewareStack

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "mcqbackend.settings"
)

django_asgi_app = get_asgi_application()

# =========================================================
# IMPORT ROUTINGS
# =========================================================

import practicalapp.routing
import cyberpracticalapp.routing

# =========================================================
# IMPORT TOKEN MIDDLEWARE
# =========================================================

from practicalapp.middleware import (
    TokenAuthMiddleware
)

# =========================================================
# MERGE WEBSOCKET ROUTES
# =========================================================

all_websocket_routes = (

    practicalapp.routing.websocket_urlpatterns +

    cyberpracticalapp.routing.websocket_urlpatterns
)

# =========================================================
# APPLICATION
# =========================================================

application = ProtocolTypeRouter({

    "http": django_asgi_app,

    "websocket": TokenAuthMiddleware(

        AuthMiddlewareStack(

            URLRouter(

                all_websocket_routes
            )
        )
    ),
})