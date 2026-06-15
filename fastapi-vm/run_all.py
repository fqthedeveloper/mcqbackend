import subprocess
import sys
import time


linux_process = None

cyber_process = None


def start_linux():

    global linux_process

    linux_process = subprocess.Popen(

        [

            sys.executable,

            "-m",

            "uvicorn",

            "app.main:app",

            # "--host",

            # "0.0.0.0",

            "--port",

            "9000",

            "--reload",
        ]
    )


def start_cyber():

    global cyber_process

    cyber_process = subprocess.Popen(

        [

            sys.executable,

            "-m",

            "uvicorn",

            "app.cyber_main:app",

            # "--host",

            # "0.0.0.0",

            "--port",

            "9001",

            "--reload",
        ]
    )


def stop_all():

    global linux_process
    global cyber_process

    if linux_process:

        linux_process.terminate()

    if cyber_process:

        cyber_process.terminate()


def main():

    try:

        print("=" * 60)
        print("Starting Linux Practical API : 9000")
        print("Starting Cyber Practical API : 9001")
        print("=" * 60)

        start_linux()

        time.sleep(2)

        start_cyber()

        while True:

            time.sleep(1)

    except KeyboardInterrupt:

        print("\nStopping all servers...")

        stop_all()


if __name__ == "__main__":

    main()