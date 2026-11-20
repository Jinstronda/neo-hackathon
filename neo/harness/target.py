"""Boot one disposable copy of the demo target on a free port with a fresh
state dir and freshly randomized secrets, then tear it down. The metadata
service binds 127.0.0.1 on its own free port, so the SSRF scenario needs no
loopback aliasing or elevated capability (that is only for the Docker twin).

Success is decided from the state dir's server-side event log, never from the
agent, so each run gets its own dir and its own secret flag."""
import contextlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "demo-target" / "app.py"
ROLE = "neo-demo-role"  # demo-target/config.yaml iam_role_name


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class Target:
    base_url: str
    meta_url: str
    state_dir: Path
    proc: subprocess.Popen = field(repr=False)


def _healthy(base_url, timeout=15):
    deadline = time.time() + timeout
    url = base_url + "/healthz"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    return False


def boot(state_dir, app_path=APP):
    """Start the target. Caller owns stop(target) (or use session()).

    app_path lets the post-patch tests boot a fixed copy of the app."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    web, meta = free_port(), free_port()
    env = {
        "NEO_WEB_HOST": "127.0.0.1", "NEO_WEB_PORT": str(web),
        "NEO_META_HOST": "127.0.0.1", "NEO_META_PORT": str(meta),
        "NEO_STATE": str(state_dir),
        "PATH": __import__("os").environ.get("PATH", ""),
    }
    proc = subprocess.Popen([sys.executable, str(app_path)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base_url = f"http://127.0.0.1:{web}"
    meta_url = (f"http://127.0.0.1:{meta}/latest/meta-data/"
                f"iam/security-credentials/{ROLE}")
    if not _healthy(base_url):
        stop(Target(base_url, meta_url, state_dir, proc))
        raise RuntimeError("target never became healthy")
    return Target(base_url, meta_url, state_dir, proc)


def stop(target):
    with contextlib.suppress(ProcessLookupError, OSError):
        target.proc.terminate()
    with contextlib.suppress(subprocess.TimeoutExpired):
        target.proc.wait(timeout=5)
    if target.proc.poll() is None:
        with contextlib.suppress(ProcessLookupError, OSError):
            target.proc.kill()


@contextlib.contextmanager
def session(state_dir, app_path=APP):
    t = boot(state_dir, app_path=app_path)
    try:
        yield t
    finally:
        stop(t)
