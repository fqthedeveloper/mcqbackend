import requests

from django.conf import settings


# =========================================================
# CREATE LAB
# =========================================================

def create_lab(payload):

    response = requests.post(

        f"{settings.CYBER_FASTAPI_VM_URL}/cyber/start",

        json=payload,

        timeout=600
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# VERIFY LAB
# =========================================================

def verify_lab(payload):

    response = requests.post(

        f"{settings.CYBER_FASTAPI_VM_URL}/cyber/verify",

        json=payload,

        timeout=600
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# DESTROY LAB
# =========================================================

def destroy_lab(payload):

    response = requests.post(

        f"{settings.CYBER_FASTAPI_VM_URL}/cyber/destroy",

        json=payload,

        timeout=600
    )

    response.raise_for_status()

    return response.json()