from typing import Dict, Any, Optional

from pydantic import BaseModel


# =========================================================
# START
# =========================================================

class CyberLabStartRequest(BaseModel):

    session_id: int

    variables: Dict[str, Any]

    attacker_script: str

    victim_script: str

    monitor_script: Optional[str] = ""
    attacker_username: str
    attacker_password: str

    victim_username: str
    victim_password: str

    monitor_username: str | None = None
    monitor_password: str | None = None


# =========================================================
# VERIFY
# =========================================================

class CyberVerifyRequest(BaseModel):

    session_id: int

    variables: Dict[str, Any]

    verify_script: str


# =========================================================
# DESTROY
# =========================================================

class CyberDestroyRequest(BaseModel):

    session_id: int