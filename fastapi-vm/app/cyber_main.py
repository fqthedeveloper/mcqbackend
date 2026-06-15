from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException

import threading
import traceback
import datetime

from .cyber_models import (

    CyberLabStartRequest,

    CyberVerifyRequest,

    CyberDestroyRequest,
)

from .cyber_runtime import (

    start_cyber_lab,

    destroy_cyber_lab,
)

from .cyber_verify import (
    verify_cyber_lab
)


# =========================================================
# APP
# =========================================================

app = FastAPI(

    title="Cyber Practical VM Service",

    version="3.0.0"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)


# =========================================================
# GLOBALS
# =========================================================

ACTIVE_SESSIONS = set()

SESSION_MUTEX = threading.Lock()

SESSION_STATUS = {}

SESSION_LOGS = {}


# =========================================================
# LOGGER
# =========================================================

def log_task(

    session_id,

    message
):

    timestamp = datetime.datetime.now().strftime(
        "%H:%M:%S"
    )

    line = (
        f"[{timestamp}] "
        f"[SESSION {session_id}] "
        f"{message}"
    )

    print(line)

    if session_id not in SESSION_LOGS:

        SESSION_LOGS[session_id] = []

    SESSION_LOGS[session_id].append(line)


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():

    return {

        "service":
            "Cyber Practical VM Service",

        "status":
            "running",
    }


# =========================================================
# START LAB
# =========================================================

@app.post("/cyber/start")
def cyber_start(
    data: CyberLabStartRequest
):

    with SESSION_MUTEX:

        if data.session_id in ACTIVE_SESSIONS:

            raise HTTPException(

                status_code=409,

                detail=
                    "Cyber lab already starting"
            )

        ACTIVE_SESSIONS.add(
            data.session_id
        )

        SESSION_STATUS[
            data.session_id
        ] = "starting"

    try:

        log_task(

            data.session_id,

            "================================================="
        )

        log_task(

            data.session_id,

            "CYBER LAB START REQUEST RECEIVED"
        )

        log_task(

            data.session_id,

            f"Session ID: {data.session_id}"
        )

        log_task(

            data.session_id,

            "Preparing isolated Kali attacker VM"
        )

        result = start_cyber_lab(

            session_id=data.session_id,

            variables=data.variables,

            attacker_script=data.attacker_script,

            victim_script=data.victim_script,

            monitor_script=data.monitor_script,

            attacker_username=data.attacker_username,

            attacker_password=data.attacker_password,

            victim_username=data.victim_username,

            victim_password=data.victim_password,

            monitor_username=data.monitor_username,

            monitor_password=data.monitor_password,
        )

        SESSION_STATUS[
            data.session_id
        ] = "running"

        log_task(

            data.session_id,

            "Cyber lab started successfully"
        )

        log_task(

            data.session_id,

            "Browser cyber lab ready"
        )

        log_task(

            data.session_id,

            "================================================="
        )

        return result

    except Exception as e:

        SESSION_STATUS[
            data.session_id
        ] = "failed"

        error_message = str(e)

        log_task(

            data.session_id,

            "CYBER LAB FAILED"
        )

        log_task(

            data.session_id,

            error_message
        )

        traceback.print_exc()

        raise HTTPException(

            status_code=500,

            detail=error_message
        )

    finally:

        with SESSION_MUTEX:

            if data.session_id in ACTIVE_SESSIONS:

                ACTIVE_SESSIONS.remove(
                    data.session_id
                )


# =========================================================
# VERIFY
# =========================================================

@app.post("/cyber/verify")
def cyber_verify(
    data: CyberVerifyRequest
):

    try:

        log_task(

            data.session_id,

            "Running cyber lab verification"
        )

        result = verify_cyber_lab(

            session_id=data.session_id,

            variables=data.variables,

            verify_script=data.verify_script,
        )

        log_task(

            data.session_id,

            f"Verification score: {result.get('score', 0)}"
        )

        return result

    except Exception as e:

        traceback.print_exc()

        log_task(

            data.session_id,

            f"Verification failed: {str(e)}"
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )


# =========================================================
# DESTROY
# =========================================================

@app.post("/cyber/destroy")
def cyber_destroy(
    data: CyberDestroyRequest
):

    try:

        log_task(

            data.session_id,

            "Destroying cyber lab"
        )

        result = destroy_cyber_lab(
            session_id=data.session_id
        )

        SESSION_STATUS[
            data.session_id
        ] = "destroyed"

        log_task(

            data.session_id,

            "Cyber lab destroyed"
        )

        return result

    except Exception as e:

        traceback.print_exc()

        log_task(

            data.session_id,

            f"Destroy failed: {str(e)}"
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )


# =========================================================
# STATUS
# =========================================================

@app.get("/cyber/status/{session_id}")
def cyber_status(
    session_id: int
):

    status = SESSION_STATUS.get(

        session_id,

        "idle"
    )

    return {

        "session_id":
            session_id,

        "status":
            status,
    }


# =========================================================
# TERMINAL LOGS
# =========================================================

@app.get("/cyber/logs/{session_id}")
def cyber_logs(
    session_id: int
):

    return {

        "session_id":
            session_id,

        "logs":
            SESSION_LOGS.get(
                session_id,
                []
            )
    }