"""Configure Nginx, a public IP TLS certificate and automatic renewal.

Run on the Ubuntu server: sudo python3 configure_https.py 43.99.87.50
Uses Let's Encrypt production certificates and accepts its subscriber terms.
No application API key is read or displayed by this installer.
"""

import argparse
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import urlopen


WEBROOT = Path("/var/www/chronomem-acme")
CERT_NAME = "chronomem-ip"
CERTBOT = Path("/opt/chronomem-certbot/bin/certbot")
SITE = Path("/etc/nginx/sites-available/chronomem")
ENABLED = Path("/etc/nginx/sites-enabled/chronomem")


def public_ip(value):
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as error:
        raise argparse.ArgumentTypeError("Enter the server's public IPv4 address.") from error
    if not address.is_global:
        raise argparse.ArgumentTypeError("The address must be a public IPv4 address.")
    return str(address)


def run(args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def nginx_config(ip, tls=False):
    ip = public_ip(ip)
    challenge = """
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/chronomem-acme;
        default_type text/plain;
    }
"""
    http = f"""server {{
    listen 80;
    server_name {ip};
    access_log off;
{challenge}
    location / {{
"""
    if not tls:
        return http + "        return 404;\n    }\n}\n"
    http += "        return 308 https://$host$request_uri;\n    }\n}\n"
    https = f"""
server {{
    listen 443 ssl;
    server_name {ip};
    ssl_certificate /etc/letsencrypt/live/{CERT_NAME}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{CERT_NAME}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    access_log off;
    error_log /var/log/nginx/chronomem-error.log warn;
    client_max_body_size 0;

    location / {{
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 1900s;
        proxy_send_timeout 1900s;
        proxy_buffering off;
    }}
}}
"""
    return http + https


def write_file(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".chronomem-tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.chmod(mode)
    temporary.replace(path)


def apply_site(text):
    if ENABLED.exists() or ENABLED.is_symlink():
        if not ENABLED.is_symlink() or ENABLED.resolve() != SITE.resolve():
            raise SystemExit("A different configuration already uses the chronomem site name.")
    previous = SITE.read_bytes() if SITE.exists() else None
    created_link = not ENABLED.is_symlink()
    write_file(SITE, text)
    if created_link:
        ENABLED.symlink_to(SITE)
    try:
        run(["/usr/sbin/nginx", "-t"])
        run(["systemctl", "reload", "nginx"])
    except subprocess.CalledProcessError:
        if previous is not None:
            SITE.write_bytes(previous)
        elif SITE.exists():
            SITE.unlink()
        if created_link and ENABLED.is_symlink():
            ENABLED.unlink()
        subprocess.run(["/usr/sbin/nginx", "-t"], check=False)
        subprocess.run(["systemctl", "reload", "nginx"], check=False)
        raise


def configure_renewal():
    hook = """#!/usr/bin/python3
import subprocess
subprocess.run(['/usr/sbin/nginx', '-t'], check=True)
subprocess.run(['/usr/bin/systemctl', 'reload', 'nginx'], check=True)
"""
    write_file(Path("/etc/letsencrypt/renewal-hooks/deploy/20-chronomem-nginx.py"), hook, 0o750)
    service = """[Unit]
Description=Renew ChronoMem IP HTTPS certificate
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/chronomem-certbot/bin/certbot renew --quiet
"""
    timer = """[Unit]
Description=Check ChronoMem certificate renewal twice daily

[Timer]
OnCalendar=*-*-* 00:00:00
OnCalendar=*-*-* 12:00:00
RandomizedDelaySec=1800
Persistent=true

[Install]
WantedBy=timers.target
"""
    write_file(Path("/etc/systemd/system/chronomem-renew.service"), service)
    write_file(Path("/etc/systemd/system/chronomem-renew.timer"), timer)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "--now", "chronomem-renew.timer"])
    run(["systemctl", "is-active", "--quiet", "chronomem-renew.timer"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ip", type=public_ip)
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0:
        raise SystemExit("Run this command with sudo in the Ubuntu server terminal.")
    if not Path("/usr/sbin/nginx").is_file():
        raise SystemExit("Install and start Nginx before running this installer.")
    if not shutil.which("curl"):
        raise SystemExit("Install curl before running this installer.")
    with urlopen("http://127.0.0.1:8000/health", timeout=5) as response:
        if json.load(response).get("status") != "ok":
            raise SystemExit("The ChronoMem API did not pass its local health check.")

    print("Step 1/5: Install Certbot in its own Python environment.", flush=True)
    if not (CERTBOT.parent / "python").is_file():
        run(["python3", "-m", "venv", "/opt/chronomem-certbot"])
    run([CERTBOT.parent / "python", "-m", "pip", "install", "--upgrade", "certbot>=5.4"])

    print("Step 2/5: Prepare HTTP certificate validation.", flush=True)
    (WEBROOT / ".well-known/acme-challenge").mkdir(parents=True, exist_ok=True)
    existing_certificate = Path(f"/etc/letsencrypt/live/{CERT_NAME}/fullchain.pem").exists()
    apply_site(nginx_config(args.ip, tls=existing_certificate))

    print("Step 3/5: Request a publicly trusted short-lived IP certificate.", flush=True)
    run([
        CERTBOT, "certonly", "--non-interactive", "--agree-tos",
        "--register-unsafely-without-email", "--preferred-profile", "shortlived",
        "--webroot", "--webroot-path", WEBROOT, "--ip-address", args.ip,
        "--cert-name", CERT_NAME, "--keep-until-expiring",
    ])

    print("Step 4/5: Enable HTTPS and automatic certificate renewal.", flush=True)
    apply_site(nginx_config(args.ip, tls=True))
    configure_renewal()

    print("Step 5/5: Test renewal and verify HTTPS without bypassing TLS checks.", flush=True)
    run([CERTBOT, "renew", "--cert-name", CERT_NAME, "--dry-run"])
    result = run([
        "curl", "--fail", "--silent", "--show-error", "--max-time", "15",
        "--connect-to", f"{args.ip}:443:127.0.0.1:443", f"https://{args.ip}/health",
    ], capture_output=True, text=True)
    health = json.loads(result.stdout)
    if health.get("status") != "ok":
        raise SystemExit("The HTTPS health response was unexpected.")
    print(json.dumps(health))
    print("ChronoMem HTTPS is ready. Automatic renewal is enabled.")
    print(f"Health: https://{args.ip}/health")
    print(f"API docs: https://{args.ip}/docs")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        print("An HTTPS setup step failed. Send the last error lines for troubleshooting.", file=sys.stderr)
        raise SystemExit(error.returncode)
