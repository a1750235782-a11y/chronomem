"""Upgrade this server to the BM25 baseline, with a database backup and code rollback."""

import ast
from contextlib import closing
from datetime import datetime, timezone
import getpass
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from urllib.request import urlopen


APP = Path("/home/admin/chronomem")
UNIT = Path("/etc/systemd/system/chronomem.service")
VERSION = "0.3.0-bm25"


def run(args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def wait_for(version):
    for attempt in range(30):
        try:
            with urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
                health = json.load(response)
            if health.get("status") == "ok" and health.get("version") == version:
                return health
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError("The updated API did not pass the versioned health check.")


def main():
    if sys.platform != "linux" or getpass.getuser() != "admin":
        raise SystemExit("Run this installer in the Ubuntu server terminal as admin, without sudo.")
    source = Path(__file__).resolve().parent
    if source == APP:
        raise SystemExit("Extract the update into /home/admin/chronomem-bm25-update first.")
    names = ["competition_app_secure.py", "lexical_memory.py", "check_server.py", "chronomem.service"]
    for name in names:
        if not (source / name).is_file():
            raise SystemExit(f"Missing update file: {name}")
        if name.endswith(".py"):
            ast.parse((source / name).read_text(encoding="utf-8"))
    python = APP / ".venv/bin/python"
    if not python.is_file() or not UNIT.is_file():
        raise SystemExit("Complete the original server installation before this upgrade.")
    if sqlite3.sqlite_version_info < (3, 24, 0):
        raise SystemExit("This SQLite version is too old for the retrieval index.")

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup = APP / "backups" / ("before-bm25-" + suffix)
    backup.mkdir(parents=True, mode=0o700)
    backup.chmod(0o700)
    for name in names:
        if (APP / name).is_file():
            shutil.copy2(APP / name, backup / name)
    shutil.copy2(UNIT, backup / "original.service")
    run(["sudo", "systemctl", "stop", "chronomem"])
    changed = False
    try:
        database = APP / "data/chronomem_contract.db"
        if database.exists():
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as old:
                with closing(sqlite3.connect(backup / "chronomem_contract.db")) as saved:
                    old.backup(saved)
            (backup / "chronomem_contract.db").chmod(0o600)
        print("Backup saved: " + str(backup), flush=True)
        changed = True
        for name in names:
            shutil.copy2(source / name, APP / name)
        run(["sudo", "install", "-m", "644", source / "chronomem.service", UNIT])
        run(["sudo", "systemctl", "daemon-reload"])
        run(["sudo", "systemctl", "start", "chronomem"])
        health = wait_for(VERSION)
        print(json.dumps(health), flush=True)
        run([python, APP / "check_server.py", "--base-url", "https://43.99.87.50", "--connect-local"])
        print("ChronoMem BM25 upgrade passed. Version: " + VERSION, flush=True)
    except Exception:
        print("Upgrade failed; restoring the previous code and service configuration.", file=sys.stderr)
        run(["sudo", "systemctl", "stop", "chronomem"])
        if changed:
            for name in names:
                if (backup / name).is_file():
                    shutil.copy2(backup / name, APP / name)
            run(["sudo", "install", "-m", "644", backup / "original.service", UNIT])
            run(["sudo", "systemctl", "daemon-reload"])
        run(["sudo", "systemctl", "start", "chronomem"])
        # The index migration only adds tables; preserve the live database and its new records.
        # The pre-upgrade SQLite backup remains available for a separate recovery if needed.
        print("Previous code restored. The database was preserved; a pre-upgrade backup is available.", file=sys.stderr)
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Upgrade stopped: " + type(error).__name__ + ". Send the final error lines for troubleshooting.", file=sys.stderr)
        raise SystemExit(1)
