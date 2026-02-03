import pyotp
import qrcode
import base64
from io import BytesIO

def generate_totp_secret():
    return pyotp.random_base32()

def get_totp_uri(user, secret):
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=user.email,
        issuer_name="Exam System"
    )

def generate_qr_code_base64(uri):
    qr = qrcode.make(uri)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()

def verify_totp(secret, code):
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)
