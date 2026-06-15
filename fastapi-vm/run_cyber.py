import subprocess
import sys


def main():

    try:

        subprocess.run(

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
            ],

            check=True
        )

    except KeyboardInterrupt:

        print("\nCyber Practical Server stopped")


if __name__ == "__main__":

    main()