"""Prepare a local secret and ignore private files without printing the key."""

from pathlib import Path
import secrets

from dotenv import dotenv_values


folder = Path(__file__).resolve().parent
env_path = folder / ".env"
existing = dotenv_values(env_path) if env_path.exists() else {}
if not existing.get("CHRONOMEM_API_KEY", ""):
    if "CHRONOMEM_API_KEY" in existing:
        raise SystemExit("CHRONOMEM_API_KEY exists but is empty. Check .env locally.")
    current = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    prefix = "\n" if current and not current.endswith("\n") else ""
    with env_path.open("a", encoding="utf-8") as env_file:
        env_file.write(prefix + "CHRONOMEM_API_KEY=" + secrets.token_urlsafe(32) + "\n")

ignore_path = folder / ".gitignore"
ignore_text = ignore_path.read_text(encoding="utf-8") if ignore_path.exists() else ""
rules = [".env", ".env.*", "!.env.example", ".venv/", "__pycache__/",
         "*.py[cod]", "*.db", "*.db-*", "*.sqlite*", "backups/", "*.bak"]
missing = [rule for rule in rules if rule not in ignore_text.splitlines()]
if missing:
    prefix = "\n" if ignore_text and not ignore_text.endswith("\n") else ""
    with ignore_path.open("a", encoding="utf-8") as ignore_file:
        ignore_file.write(prefix + "\n".join(missing) + "\n")

print("Ready: local API key configured; private files added to .gitignore.")
print("The key was not printed. Keep .env private.")
