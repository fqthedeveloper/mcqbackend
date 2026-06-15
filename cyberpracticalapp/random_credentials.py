# cyber/random_credentials.py

import secrets
import string


def generate_username():

    chars = (
        string.ascii_lowercase +
        string.digits
    )

    return "student_" + "".join(
        secrets.choice(chars)
        for _ in range(8)
    )


def generate_password():

    chars = (
        string.ascii_letters +
        string.digits +
        "!@#$%^&*"
    )

    return "".join(
        secrets.choice(chars)
        for _ in range(16)
    )