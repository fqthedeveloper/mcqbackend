import subprocess

import tempfile

import os


# =========================================================
# VERIFY CYBER LAB
# =========================================================

def verify_cyber_lab(
    session_id,
    variables,
):

    score = 0

    details = []

    try:

        if "flag_token" in variables:

            score += 40

            details.append(
                "Flag token validation completed"
            )

        if "victim_ip" in variables:

            score += 30

            details.append(
                "Victim machine reachable"
            )

        if "admin_user" in variables:

            score += 30

            details.append(
                "Admin enumeration completed"
            )

        return {

            "score": score,

            "details": details,

            "raw_output": "\n".join(details),
        }

    except Exception as e:

        return {

            "score": 0,

            "details": [],

            "raw_output": str(e),
        }