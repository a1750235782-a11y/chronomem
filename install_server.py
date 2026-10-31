"""Install the prepared ChronoMem service on this Ubuntu server as admin."""

import getpass
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen


def run(args):
    subprocess.run(args, check=True)


def main():
    if sys.platform != "linux" or getpass.getuser() != "admin":
        raise SystemExit("Run this installer in the Ubuntu terminal as admin.")
    app_dir = Path("/home/admin/chronomem")
    python = app_dir / ".venv/bin/python"
    for name in ("competition_app_secure.py", "requirements.txt", "setup_local_key.py", "chronomem.service"):
        if not (app_dir / name).is_file():
            raise SystemExit(f"Missing file: {app_dir / name}. Extract the archive first.")
    if not python.is_file():
        raise SystemExit("The virtual environment is missing. Complete environment setup first.")

    run([str(python), "-c", "import fastapi, uvicorn, pydantic, dotenv"])
    run([str(python), str(app_dir / "setup_local_key.py")])
    (app_dir / ".env").chmod(0o600)
    data_dir = app_dir / "data"
    data_dir.mkdir(mode=0o700, exist_ok=True)
    data_dir.chmod(0o700)

    run(["sudo", "install", "-m", "644", str(app_dir / "chronomem.service"),
         "/etc/systemd/system/chronomem.service"])
    run(["sudo", "systemctl", "daemon-reload"])
    run(["sudo", "systemctl", "enable", "chronomem.service"])
    run(["sudo", "systemctl", "restart", "chronomem.service"])

    for attempt in range(20):
        active = subprocess.run(
            ["sudo", "systemctl", "is-active", "--quiet", "chronomem.service"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0
        if active:
            try:
                with urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
                    health = json.load(response)
                if health.get("status") == "ok" and health.get("version") == "0.3.0-bm25":
                    print(json.dumps(health))
                    print("ChronoMem service is running. Automatic startup is enabled.")
                    return
            except (OSError, ValueError):
                pass
        time.sleep(1)

    print("Startup did not pass the health check. Recent service logs:", file=sys.stderr)
    run(["sudo", "journalctl", "-u", "chronomem.service", "-n", "30", "--no-pager"])
    raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print("A setup command failed. Send the error above for troubleshooting.", file=sys.stderr)
        raise SystemExit(error.returncode)
