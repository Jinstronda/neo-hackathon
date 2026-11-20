#!/usr/bin/env python3
"""SnapVault — the NEO demo target. A small profile API with three textbook,
independently exploitable, independently patchable bug classes:

  A sql-injection auth bypass   POST /login   (string-concatenated sqlite query)
  B ssrf -> metadata -> reuse   POST /import-avatar + the internal metadata
                                service + GET /admin/export (leaked key accepted)
  C weak-jwt-secret forgery     GET /me, GET /admin/whoami (HS256, guessable secret)

Stdlib only. Every security-relevant event is appended as one JSON line to
$NEO_STATE/events.jsonl. The flag checks in ../checks read ONLY that server-side
log, never an agent's report. Secrets, the admin password and the flag are
randomized per run, so an admin login or a flag read can only come from the
exploit, not from guessing.

Config comes from config.yaml, read with a stdlib line parser (the file is
flat scalars only, so PyYAML would be a dependency for four key: value lines).
The intended fixes are documented in FIXES.md and are NOT applied here — the
blue agent applies them live.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get("NEO_STATE", HERE.parent / "runs" / "twin-state"))
STATE.mkdir(parents=True, exist_ok=True)
EVENTS = STATE / "events.jsonl"
DB = STATE / "app.db"

WEB_HOST = os.environ.get("NEO_WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("NEO_WEB_PORT", "8080"))
# The internal metadata service. In Docker this is the real link-local AWS IMDS
# address on port 80 (entrypoint.sh aliases it onto lo). Locally, 127.0.0.1.
META_HOST = os.environ.get("NEO_META_HOST", "169.254.169.254")
META_PORT = int(os.environ.get("NEO_META_PORT", "80"))

# Bug C: a guessable HS256 secret hardcoded in the source. The fix replaces this
# with secrets.token_urlsafe(32) generated at startup (see FIXES.md).
WEAK_JWT_SECRET = secrets.token_urlsafe(32)

def _load_flat_config(path):
    cfg = {}
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        cfg[key.strip()] = value.strip()
    return cfg


CFG = _load_flat_config(HERE / "config.yaml")
ROLE_NAME = CFG["iam_role_name"]
GUEST_USER = CFG["guest_username"]
GUEST_PASS = CFG["guest_password"]

# Randomized per run. Unguessable -> an admin login or flag read proves the exploit.
# DEMO_FLAG lets the twin pin the flag it will check for (infra/twin_local sets it);
# with no env it is random, so the local harness still randomizes per process.
ADMIN_PASS = secrets.token_hex(16)
META_KEY = "ASIA" + secrets.token_hex(8).upper()
FLAG = os.environ.get("DEMO_FLAG") or ("NEO{" + secrets.token_hex(8) + "}")

_lock = threading.Lock()
# jti -> role the server actually issued. Lets the JWT check tell a forged admin
# token (role=admin with an unregistered/guest jti) from a server-issued one.
_issued = {}


def log_event(etype, **detail):
    with _lock:
        with EVENTS.open("a") as f:
            f.write(json.dumps({"ts": round(time.time(), 3), "type": etype,
                                "detail": detail}) + "\n")


def init_db():
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE users (username TEXT, password TEXT, role TEXT)")
    con.executemany("INSERT INTO users VALUES (?,?,?)", [
        ("admin", ADMIN_PASS, "admin"),
        (GUEST_USER, GUEST_PASS, "guest"),
    ])
    con.commit()
    con.close()


# ------------------------------------------------------------------ minimal JWT

def _b64u(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def _b64u_dec(s):
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def jwt_encode(payload, secret):
    head = _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    signing = head + b"." + body
    sig = _b64u(hmac.new(secret.encode(), signing, hashlib.sha256).digest())
    return (signing + b"." + sig).decode()


def jwt_decode(token, secret):
    head, body, sig = token.split(".")
    signing = (head + "." + body).encode()
    expect = _b64u(hmac.new(secret.encode(), signing, hashlib.sha256).digest()).decode()
    if not hmac.compare_digest(expect, sig):
        raise ValueError("bad signature")
    return json.loads(_b64u_dec(body))


# --------------------------------------------------------------- metadata service

class MetaHandler(BaseHTTPRequestHandler):
    """Cloud-instance metadata service, AWS IMDS shaped. Reachable only from this
    host, so an attacker needs the SSRF to touch it."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == f"/latest/meta-data/iam/security-credentials/{ROLE_NAME}":
            log_event("internal_fetch", url=self.path)
            body = json.dumps({
                "Code": "Success", "Type": "AWS-HMAC",
                "AccessKeyId": "ASIADEMOACCESSKEY",
                "SecretAccessKey": META_KEY,
                "Token": secrets.token_hex(8),
            }).encode()
            self._ok(body)
        elif self.path == "/latest/meta-data/iam/security-credentials/":
            log_event("internal_fetch", url=self.path)
            self._ok(ROLE_NAME.encode(), "text/plain")
        else:
            self.send_response(404)
            self.end_headers()

    def _ok(self, body, ctype="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# -------------------------------------------------------------------- web service

INDEX = """<!doctype html><title>SnapVault</title><h1>SnapVault</h1>
<p>Profile avatars are imported from a URL.</p>
<form method=post action=/login>user <input name=username> pass <input name=password>
<button>Log in</button></form>
<!-- ops: admin export at /admin/export needs the instance role key -->"""


class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    # ---- helpers
    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _html(self, code, body):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n).decode() if n else ""
        ctype = self.headers.get("Content-Type", "")
        if ctype.startswith("application/json"):
            try:
                return json.loads(raw) if raw else {}
            except ValueError:
                return {}
        form = urllib.parse.parse_qs(raw)
        return {k: v[0] for k, v in form.items()}

    def _bearer(self):
        auth = self.headers.get("Authorization", "")
        return auth[7:] if auth.startswith("Bearer ") else ""

    # ---- routes
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._html(200, INDEX)
        elif path == "/healthz":
            self._json(200, {"ok": True})
        elif path == "/me":
            self.route_me()
        elif path == "/admin/whoami":
            self.route_admin_whoami()
        elif path == "/admin/export":
            self.route_admin_export()
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/login":
            self.route_login()
        elif path == "/import-avatar":
            self.route_import_avatar()
        else:
            self._json(404, {"error": "not found"})

    def route_login(self):
        d = self._body()
        user = d.get("username", "")
        pw = d.get("password", "")
        log_event("login_attempt", username=user)
        con = sqlite3.connect(DB)
        try:
            q = ("SELECT username, role FROM users "
                 "WHERE username = ? AND password = ?")
            row = con.execute(q, (user, pw)).fetchone()
        except sqlite3.Error as e:
            self._json(400, {"error": f"query error: {e}"})
            return
        finally:
            con.close()
        if not row:
            self._json(401, {"error": "invalid credentials"})
            return
        username, role = row
        log_event("login_success", username=username, role=role, submitted=user)
        jti = secrets.token_hex(8)
        _issued[jti] = role
        token = jwt_encode({"sub": username, "role": role, "jti": jti}, WEAK_JWT_SECRET)
        self._json(200, {"token": token, "role": role})

    def route_me(self):
        try:
            claims = jwt_decode(self._bearer(), WEAK_JWT_SECRET)
        except Exception:  # noqa: BLE001
            self._json(401, {"error": "invalid token"})
            return
        self._json(200, {"sub": claims.get("sub"), "role": claims.get("role")})

    def route_admin_whoami(self):
        try:
            claims = jwt_decode(self._bearer(), WEAK_JWT_SECRET)
        except Exception:  # noqa: BLE001
            self._json(401, {"error": "invalid token"})
            return
        if claims.get("role") != "admin":
            self._json(403, {"error": "admin only"})
            return
        jti = claims.get("jti")
        if _issued.get(jti) == "admin":
            # a token the server really issued as admin (e.g. the SQLi path)
            log_event("admin_whoami", jti=jti, issued="server")
            self._json(200, {"role": "admin", "note": "server-issued admin token"})
        else:
            # Bug C exploited: valid admin-role signature the server never issued
            log_event("jwt_forged_admin", jti=jti, sub=claims.get("sub"))
            self._json(200, {"role": "admin", "flag": FLAG})

    def route_import_avatar(self):
        d = self._body()
        url = d.get("url", "")
        if not url.startswith(("http://", "https://")):
            self._json(400, {"error": "url must be http(s)"})
            return
        host = urllib.parse.urlparse(url).hostname
        log_event("avatar_fetch", url=url, host=host)
        if not host or host == META_HOST:
            self._json(400, {"error": "forbidden host"})
            return
        try:
            import ipaddress
            import socket
            for _, _, _, _, sockaddr in socket.getaddrinfo(host, None):
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    self._json(400, {"error": "forbidden host"})
                    return
        except Exception:
            self._json(400, {"error": "invalid host"})
            return
        try:
            # Bug B: fetches any user-supplied URL server-side, no allowlist and
            # no block on internal/link-local addresses -> SSRF. The response body
            # is reflected to the caller, so a fetched secret leaks.
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = resp.read(2048).decode("utf-8", "replace")
                ctype = resp.headers.get("Content-Type", "")
        except Exception as e:  # noqa: BLE001
            self._json(502, {"error": f"fetch failed: {type(e).__name__}"})
            return
        self._json(200, {"fetched": True, "content_type": ctype, "preview": body})

    def route_admin_export(self):
        key = self.headers.get("X-Amz-Security-Token", "") or self.headers.get("X-Api-Key", "")
        if key and hmac.compare_digest(key, META_KEY):
            # Broken access control: the internal instance key is accepted from
            # any origin (credential reuse completes the SSRF chain).
            log_event("admin_key_used", key_prefix=key[:4])
            log_event("flag_read", via="admin export")
            self._json(200, {"flag": FLAG, "export": "user-db-dump"})
        else:
            self._json(403, {"error": "instance role key required"})


def main():
    init_db()
    log_event("startup", app=CFG["app_name"], meta_host=META_HOST, meta_port=META_PORT)
    try:
        meta = ThreadingHTTPServer((META_HOST, META_PORT), MetaHandler)
    except OSError as e:
        print(f"[snapvault] metadata bind {META_HOST}:{META_PORT} failed ({e}); "
              f"falling back to 127.0.0.1:9253", flush=True)
        meta = ThreadingHTTPServer(("127.0.0.1", 9253), MetaHandler)
    threading.Thread(target=meta.serve_forever, daemon=True).start()
    web = ThreadingHTTPServer((WEB_HOST, WEB_PORT), WebHandler)
    print(f"[snapvault] web http://{WEB_HOST}:{WEB_PORT}  meta {META_HOST}:{META_PORT}  "
          f"state {STATE}", flush=True)
    web.serve_forever()


if __name__ == "__main__":
    main()
