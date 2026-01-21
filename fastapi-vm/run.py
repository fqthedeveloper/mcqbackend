import subprocess
import sys


def main():
    try:
        subprocess.run(
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
            ],
            check=True
        )
    except KeyboardInterrupt:
        print("\nServer stopped")


if __name__ == "__main__":
    main()
