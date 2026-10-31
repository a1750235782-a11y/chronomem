"""Check a ChronoMem API using synthetic data, without printing its key.

On this server:
  .venv/bin/python check_server.py --base-url https://43.99.87.50 --connect-local
This is a participant self-check, not the official AML Smoke evaluation.
"""

import argparse
import http.client
import json
from pathlib import Path
import socket
import ssl
import subprocess
import sys
from urllib.parse import urlparse
import uuid

from dotenv import dotenv_values


class APIClient:
    def __init__(self, base_url, key, connect_local=False):
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Supply an HTTP(S) base URL.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("Supply only the API origin, without credentials or a path.")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("Use HTTPS for an external API.")
        if connect_local and parsed.scheme != "https":
            raise ValueError("The server-local connection mode requires HTTPS.")
        self.host = parsed.hostname
        self.port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.https = parsed.scheme == "https"
        self.key = key
        self.connect_local = connect_local

    def request(self, method, path, body=None, auth="valid"):
        context = ssl.create_default_context() if self.https else None
        if self.https:
            conn = http.client.HTTPSConnection(self.host, self.port, timeout=30, context=context)
        else:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
        if self.connect_local:
            # Connect to this server's Nginx while verifying the public IP's TLS identity.
            raw = socket.create_connection(("127.0.0.1", self.port), timeout=30)
            try:
                conn.sock = context.wrap_socket(raw, server_hostname=self.host)
            except Exception:
                raw.close()
                raise
        headers = {"Accept": "application/json"}
        if auth != "none":
            headers["X-Api-Key"] = self.key if auth == "valid" else "incorrect-test-key"
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            conn.request(method, path, body=data, headers=headers)
            response = conn.getresponse()
            raw = response.read()
            try:
                result = json.loads(raw)
            except (ValueError, UnicodeError):
                result = None
            return response.status, result
        finally:
            conn.close()


def require(condition, label):
    if not condition:
        raise RuntimeError(label + " failed; no key has been printed.")
    print("PASS: " + label, flush=True)


def run_checks(client):
    namespace = "selfcheck:" + uuid.uuid4().hex
    user_a, user_b = namespace + ":a", namespace + ":b"
    write = {
        "request_id": namespace + ":write-1",
        "user_id": user_a,
        "session_id": namespace + ":session",
        "messages": [
            {"role": "user", "content": "I like coffee and Python."},
            {"role": "assistant", "content": "Coffee meetup on Friday."},
        ],
    }
    query = {"query": "coffee", "user_id": user_a, "top_k": 100}
    status, health = client.request("GET", "/health", auth="none")
    require(status == 200 and health and health.get("status") == "ok", "health")
    for path, body in (("/add", write), ("/search", query)):
        require(client.request("POST", path, body, auth="none")[0] == 401, path + " rejects missing key")
        require(client.request("POST", path, body, auth="wrong")[0] == 401, path + " rejects incorrect key")
    status, added = client.request("POST", "/add", write)
    expected = {"success": True, "request_id": write["request_id"], "user_id": user_a, "session_id": write["session_id"]}
    require(status == 200 and added == expected, "Add HTTP 200 and exact echoed identifiers")
    status, found = client.request("POST", "/search", query)
    records = found.get("data", []) if isinstance(found, dict) else []
    require(status == 200 and len(records) == 2 and all(isinstance(m.get("id"), str) and m["id"] and m.get("content") for m in records), "Search returns memory evidence")
    status, isolated = client.request("POST", "/search", {**query, "user_id": user_b})
    require(status == 200 and isolated == {"data": []}, "user isolation")
    status, retry = client.request("POST", "/add", write)
    again_status, again = client.request("POST", "/search", query)
    require(status == 200 and retry == expected and again_status == 200 and again == found, "identical Add retry does not duplicate memories")
    status, limited = client.request("POST", "/search", {**query, "top_k": 1})
    require(status == 200 and limited == {"data": records[:1]}, "top_k limit")
    status, empty = client.request("POST", "/search", {**query, "query": "unmatched-" + namespace})
    require(status == 200 and empty == {"data": []}, "no-match response")
    status, invalid = client.request("POST", "/search", {**query, "top_k": 0})
    require(status in {400, 422}, "invalid top_k rejected")
    status, natural = client.request("POST", "/search", {**query, "query": "What coffee do I like?", "top_k": 1})
    require(status == 200 and natural and len(natural.get("data", [])) == 1 and "I like coffee and Python." in natural["data"][0]["content"], "natural question retrieves supporting evidence")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://43.99.87.50")
    parser.add_argument("--key-file", type=Path, default=Path("/home/admin/chronomem/.env"))
    parser.add_argument("--connect-local", action="store_true")
    args = parser.parse_args()
    key = dotenv_values(args.key_file).get("CHRONOMEM_API_KEY")
    if not key:
        raise SystemExit("No API key found in the specified local configuration file.")
    client = APIClient(args.base_url, key, args.connect_local)
    run_checks(client)
    if args.connect_local:
        require(subprocess.run(["systemctl", "is-enabled", "--quiet", "chronomem"], check=False).returncode == 0, "API automatic startup")
        require(subprocess.run(["systemctl", "is-active", "--quiet", "chronomem-renew.timer"], check=False).returncode == 0, "certificate renewal timer active")
        print("TLS identity was verified against the public IP; HTTPS requests were routed locally through Nginx.")
    print("SELF-CHECK PASSED. This is not an official AML Smoke result.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Show only the exception type and our own validation labels, never credentials.
        if isinstance(error, RuntimeError):
            print("SELF-CHECK FAILED: " + str(error), file=sys.stderr)
        else:
            print("SELF-CHECK FAILED: " + type(error).__name__ + ". Send the last output lines for troubleshooting.", file=sys.stderr)
        raise SystemExit(1)
