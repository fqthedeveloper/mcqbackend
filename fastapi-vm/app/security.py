from fastapi import Header, HTTPException


def api_key_guard(x_api_key: str = Header(None)):
    if x_api_key != "SECRET_KEY_123":
        raise HTTPException(status_code=401, detail="Unauthorized")
