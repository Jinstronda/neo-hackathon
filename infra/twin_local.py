"""Local twin: build the demo image, run a throwaway copy on a random free
port with its own state dir, hand back its URL, tear it down.

This is the default backend the engine uses. The demo app randomizes its flag,
admin password and metadata key per run and logs every security-relevant event
to $NEO_STATE/events.jsonl, so success is decided from that server-side log (by
checks/), never from what a red agent claims. We bind-mount the state dir so the
host can read that log while the twin is still up.

The Dockerfile lives in infra/ (demo-target/ is left untouched), so we build the
demo-target context with `-f infra/Dockerfile`. Uses the docker CLI over
subprocess; no SDK dep."""
import argparse
import json
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CONTEXT = REPO / "demo-target"
DEFAULT_DOCKERFILE = REPO / "infra" / "Dockerfile"
DEFAULT_HEALTH = "/"          # app serves 200 on / ; it has no /healthz
DEFAULT_PORT = 8080           # NEO_WEB_PORT the demo app listens on in-container
STATE_ROOT = REPO / "runs" / "tmp"   # gitignored; Docker Desktop shares /Users


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, check=True, **kw)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def new_flag():
    return "FLAG{" + secrets.token_hex(16) + "}"


def build_image(context=DEFAULT_CONTEXT, tag=None, dockerfile=DEFAULT_DOCKERFILE):
    context = Path(context)
    dockerfile = Path(dockerfile)
    if not dockerfile.exists():
        raise FileNotFoundError(f"no Dockerfile at {dockerfile}")
    tag = tag or f"neo-twin:{secrets.token_hex(4)}"
    _run(["docker", "build", "-q", "-f", str(dockerfile), "-t", tag, str(context)])
    return tag


@dataclass
class Twin:
    id: str
    container: str
    base_url: str
    image: str
    state_dir: Path
    flag: str  # the twin's label flag; the app logs its own, read server-side

    def event(self, where="local"):
        # for Journal.emit("twin_create", **twin.event())
        return {"twin_id": self.id, "where": where, "image": self.image}


def boot(image, *, container_port=DEFAULT_PORT, env=None):
    """Start a disposable twin with its own mounted state dir. NET_ADMIN lets the
    entrypoint alias the metadata IP onto lo (SSRF chain); without it the app
    degrades to a loopback metadata service."""
    twin_id = "twin-" + secrets.token_hex(4)
    port = free_port()
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    state_dir = Path(tempfile.mkdtemp(prefix=f"{twin_id}-", dir=STATE_ROOT))
    cmd = ["docker", "run", "-d", "--rm", "--name", twin_id,
           "--cap-add", "NET_ADMIN",
           "-p", f"127.0.0.1:{port}:{container_port}",
           "-v", f"{state_dir}:/state", "-e", "NEO_STATE=/state"]
    for k, v in (env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    cmd.append(image)
    container = _run(cmd).stdout.strip()
    return Twin(twin_id, container, f"http://127.0.0.1:{port}", image, state_dir, new_flag())


def wait_health(base_url, path=DEFAULT_HEALTH, timeout=40):
    """Poll until the health endpoint answers 2xx, or raise on timeout."""
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if 200 <= r.status < 300:
                    return r.status
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            last = e
        time.sleep(0.5)
    raise TimeoutError(f"{url} not healthy in {timeout}s (last: {last})")


def teardown(twin):
    if isinstance(twin, Twin):
        subprocess.run(["docker", "rm", "-f", twin.container], capture_output=True, text=True)
        shutil.rmtree(twin.state_dir, ignore_errors=True)
    else:
        subprocess.run(["docker", "rm", "-f", twin], capture_output=True, text=True)


def up(context=DEFAULT_CONTEXT, *, health=DEFAULT_HEALTH, container_port=DEFAULT_PORT,
       dockerfile=DEFAULT_DOCKERFILE):
    """Build + boot + wait. Caller owns teardown(twin)."""
    image = build_image(context, dockerfile=dockerfile)
    twin = boot(image, container_port=container_port)
    wait_health(twin.base_url, health)
    return twin


def _selftest(args):
    """Build, boot, hit health, tear down. Proves the chain end to end."""
    print(f"building image from {args.context} via {args.dockerfile} ...", file=sys.stderr)
    twin = None
    try:
        twin = up(args.context, health=args.health, container_port=args.port,
                  dockerfile=args.dockerfile)
        print(json.dumps({"ok": True, "twin_id": twin.id, "base_url": twin.base_url,
                          "image": twin.image, "health": args.health}))
        return 0
    finally:
        if twin:
            teardown(twin)
            print(f"tore down {twin.id}", file=sys.stderr)


def main(argv=None):
    p = argparse.ArgumentParser(description="NEO local twin")
    p.add_argument("--context", default=str(DEFAULT_CONTEXT),
                   help="build context (demo-target)")
    p.add_argument("--dockerfile", default=str(DEFAULT_DOCKERFILE),
                   help="path to the Dockerfile (default infra/Dockerfile)")
    p.add_argument("--health", default=DEFAULT_HEALTH)
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="container listen port")
    p.add_argument("--selftest", action="store_true",
                   help="build, boot, check health, tear down")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest(args)
    twin = up(args.context, health=args.health, container_port=args.port,
              dockerfile=args.dockerfile)
    print(json.dumps({"twin_id": twin.id, "container": twin.container,
                      "base_url": twin.base_url, "image": twin.image}))
    print(f"running; tear down with: docker rm -f {twin.container}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
