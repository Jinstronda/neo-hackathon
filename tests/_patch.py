"""Apply the documented fixes (demo-target/FIXES.md) to the app source. The
post-patch tests boot the result and prove every exploit dies. Each anchor must
match the live app.py, so this doubles as a check that FIXES.md stays accurate:
a drifted anchor raises here instead of silently skipping the fix."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP = REPO / "demo-target" / "app.py"

# (label, before, after)
FIXES = [
    ("A sql-injection",
     '            q = ("SELECT username, role FROM users "\n'
     '                 f"WHERE username = \'{user}\' AND password = \'{pw}\'")\n'
     '            row = con.execute(q).fetchone()',
     '            row = con.execute(\n'
     '                "SELECT username, role FROM users WHERE username = ? AND password = ?",\n'
     '                (user, pw)).fetchone()'),

    ("B ssrf allowlist",
     '        host = urllib.parse.urlparse(url).hostname\n'
     '        log_event("avatar_fetch", url=url, host=host)',
     '        host = urllib.parse.urlparse(url).hostname\n'
     '        import ipaddress, socket as _socket\n'
     '        try:\n'
     '            _addrs = {ai[4][0] for ai in _socket.getaddrinfo(host, None)}\n'
     '        except _socket.gaierror:\n'
     '            self._json(400, {"error": "cannot resolve host"})\n'
     '            return\n'
     '        for _a in _addrs:\n'
     '            _ip = ipaddress.ip_address(_a)\n'
     '            if _ip.is_private or _ip.is_loopback or _ip.is_link_local or _ip.is_reserved:\n'
     '                log_event("ssrf_blocked", url=url, host=host)\n'
     '                self._json(400, {"error": "refusing to fetch internal address"})\n'
     '                return\n'
     '        log_event("avatar_fetch", url=url, host=host)'),

    ("C weak jwt secret",
     'WEAK_JWT_SECRET = "neo-demo-secret"',
     'WEAK_JWT_SECRET = os.environ.get("JWT_SECRET") or secrets.token_urlsafe(32)'),
]


def apply(src=None):
    text = src if src is not None else APP.read_text()
    for label, before, after in FIXES:
        if before not in text:
            raise AssertionError(f"fix anchor missing for {label}; FIXES.md drifted from app.py")
        text = text.replace(before, after, 1)
    return text


def write_patched(dest_dir):
    """Copy the demo target into dest_dir with the fixes applied; return app path."""
    import shutil
    src = APP.parent
    shutil.copytree(src, dest_dir, dirs_exist_ok=True)
    app = Path(dest_dir) / "app.py"
    app.write_text(apply(app.read_text()))
    return app
