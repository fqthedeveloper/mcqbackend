import os
import json
from datetime import datetime

from django.conf import settings


# =========================================================
# HISTORY ROOT
# =========================================================

CYBER_HISTORY_ROOT = os.path.join(
    settings.MEDIA_ROOT,
    'cyber_history'
)

os.makedirs(CYBER_HISTORY_ROOT, exist_ok=True)


# =========================================================
# SESSION DIRECTORY
# =========================================================

def get_session_history_dir(session):

    session_dir = os.path.join(
        CYBER_HISTORY_ROOT,
        f'session_{session.id}'
    )

    os.makedirs(session_dir, exist_ok=True)

    return session_dir


# =========================================================
# SAVE COMMAND HISTORY
# =========================================================

def save_command_history(
    session,
    machine_role,
    commands
):

    session_dir = get_session_history_dir(session)

    command_file = os.path.join(
        session_dir,
        f'{machine_role}_commands.log'
    )

    with open(
        command_file,
        'a',
        encoding='utf-8'
    ) as f:

        for command in commands:

            line = (
                f'[{datetime.now()}] '
                f'{command}\n'
            )

            f.write(line)

    return command_file


# =========================================================
# SAVE TERMINAL OUTPUT
# =========================================================

def save_terminal_output(
    session,
    machine_role,
    output
):

    session_dir = get_session_history_dir(session)

    output_file = os.path.join(
        session_dir,
        f'{machine_role}_terminal.log'
    )

    with open(
        output_file,
        'a',
        encoding='utf-8'
    ) as f:

        f.write(
            f'\n\n[{datetime.now()}]\n'
        )

        f.write(output)

        f.write('\n')

    return output_file


# =========================================================
# SAVE MACHINE METADATA
# =========================================================

def save_machine_metadata(
    session,
    metadata
):

    session_dir = get_session_history_dir(session)

    metadata_file = os.path.join(
        session_dir,
        'machines.json'
    )

    with open(
        metadata_file,
        'w',
        encoding='utf-8'
    ) as f:

        json.dump(
            metadata,
            f,
            indent=4
        )

    return metadata_file


# =========================================================
# SAVE SESSION VARIABLES
# =========================================================

def save_session_variables(
    session,
    variables
):

    session_dir = get_session_history_dir(session)

    variables_file = os.path.join(
        session_dir,
        'variables.json'
    )

    with open(
        variables_file,
        'w',
        encoding='utf-8'
    ) as f:

        json.dump(
            variables,
            f,
            indent=4
        )

    return variables_file


# =========================================================
# SAVE VERIFICATION OUTPUT
# =========================================================

def save_verification_output(
    session,
    output
):

    session_dir = get_session_history_dir(session)

    verify_file = os.path.join(
        session_dir,
        'verification.log'
    )

    with open(
        verify_file,
        'w',
        encoding='utf-8'
    ) as f:

        f.write(output)

    return verify_file


# =========================================================
# SAVE SCORE REPORT
# =========================================================

def save_score_report(
    session,
    report
):

    session_dir = get_session_history_dir(session)

    score_file = os.path.join(
        session_dir,
        'score.json'
    )

    with open(
        score_file,
        'w',
        encoding='utf-8'
    ) as f:

        json.dump(
            report,
            f,
            indent=4
        )

    return score_file


# =========================================================
# LOAD SESSION HISTORY
# =========================================================

def load_session_history(session):

    session_dir = get_session_history_dir(session)

    data = {}

    for filename in os.listdir(session_dir):

        full_path = os.path.join(
            session_dir,
            filename
        )

        if os.path.isfile(full_path):

            with open(
                full_path,
                'r',
                encoding='utf-8',
                errors='ignore'
            ) as f:

                data[filename] = f.read()

    return data


# =========================================================
# DELETE SESSION HISTORY
# =========================================================

def delete_session_history(session):

    session_dir = get_session_history_dir(session)

    if not os.path.exists(session_dir):
        return False

    for root, dirs, files in os.walk(
        session_dir,
        topdown=False
    ):

        for file in files:

            os.remove(
                os.path.join(root, file)
            )

        for directory in dirs:

            os.rmdir(
                os.path.join(root, directory)
            )

    os.rmdir(session_dir)

    return True


# =========================================================
# CREATE SESSION SNAPSHOT
# =========================================================

def create_session_snapshot(session):

    session_dir = get_session_history_dir(session)

    snapshot = {

        'session_id': session.id,

        'user': str(session.user),

        'task': session.task.title,

        'status': session.status,

        'score': session.obtained_marks,

        'percentage': session.percentage,

        'passed': session.is_passed,

        'start_time': str(session.start_time),

        'end_time': str(session.end_time),

        'machines': []
    }

    for machine in session.machines.all():

        snapshot['machines'].append({

            'role': machine.role,

            'vm_name': machine.vm_name,

            'vm_ip': machine.vm_ip,

            'status': machine.status,

            'username': machine.username,
        })

    snapshot_file = os.path.join(
        session_dir,
        'snapshot.json'
    )

    with open(
        snapshot_file,
        'w',
        encoding='utf-8'
    ) as f:

        json.dump(
            snapshot,
            f,
            indent=4
        )

    return snapshot_file