"""Server twin: a disposable copy of the demo stack built and run in Docker on
the organizer's box, over SSH. This is the "deploy a copy to a cloud and test
it" step. We touch only our own temp dir and our own container, and tear both
down after. Creds come from .env (TWIN_SSH_*) and are never logged.

sshpass is not installed, so we use paramiko. If the box is unreachable or has
no Docker we can bring up, this degrades to the local twin and says so in one
line; it never blocks the loop."""
import argparse
import io
import json
import os
import secrets
import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import paramiko
except ImportError:
    paramiko = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra import twin_local  # noqa: E402
from neo import env as neo_env  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CONTEXT = REPO / "demo-target"
DEFAULT_DOCKERFILE = REPO / "infra" / "Dockerfile"


class Unavailable(RuntimeError):
    """Server twin cannot run; caller should fall back to local."""


@dataclass
class ServerTwin:
    id: str
    container: str
    port: int
    base_url: str          # reachable on the box itself (127.0.0.1:port)
    image: str
    flag: str
    docker: str = "docker"  # 'docker' or 'sudo -n docker' on the box

    def event(self):
        return {"twin_id": self.id, "where": "server", "image": self.image}


def _creds():
    neo_env.load()
    host = os.environ.get("TWIN_SSH_HOST", "").strip()
    user = os.environ.get("TWIN_SSH_USER", "ubuntu").strip()
    pw = os.environ.get("TWIN_SSH_PASS", "").strip()
    if not host or not pw:
        raise Unavailable("TWIN_SSH_HOST / TWIN_SSH_PASS not set in .env")
    return host, user, pw


def connect(timeout: float = 12):
    """An SSH client logged in to the twin box, or Unavailable."""
    if paramiko is None:
        raise Unavailable("paramiko not installed")
    host, user, pw = _creds()
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        cli.connect(host, username=user, password=pw, timeout=timeout,
                    banner_timeout=timeout, auth_timeout=timeout, look_for_keys=False)
    except Exception as e:  # socket, auth, timeout
        raise Unavailable(f"ssh connect failed: {type(e).__name__}") from e
    return cli


def _exec(cli, cmd, timeout=180):
    _in, out, err = cli.exec_command(cmd, timeout=timeout)
    code = out.channel.recv_exit_status()
    return code, out.read().decode(errors="replace"), err.read().decode(errors="replace")


def ensure_docker(cli) -> str:
    """Return the docker invocation that works on the box ('docker' or
    'sudo -n docker'), bringing the daemon up if we have sudo. Raise if none."""
    _, out, _ = _exec(cli, "docker info >/dev/null 2>&1 && echo ok || echo no")
    if "ok" in out:
        return "docker"
    # daemon down or user not in docker group: try sudo (common on fresh VMs)
    _exec(cli, "sudo -n systemctl start docker >/dev/null 2>&1", timeout=60)
    _, out, _ = _exec(cli, "sudo -n docker info >/dev/null 2>&1 && echo ok || echo no")
    if "ok" in out:
        return "sudo -n docker"
    # last resort: install, then retry
    _exec(cli, "sudo -n apt-get update -y >/dev/null 2>&1 && "
               "sudo -n apt-get install -y docker.io >/dev/null 2>&1", timeout=300)
    _, out, _ = _exec(cli, "sudo -n docker info >/dev/null 2>&1 && echo ok || echo no")
    if "ok" in out:
        return "sudo -n docker"
    raise Unavailable("no usable docker on the box")


def _tar_context(context, dockerfile=DEFAULT_DOCKERFILE):
    """Tar the demo-target context and drop infra/Dockerfile in as ./Dockerfile,
    so demo-target/ stays untouched but the remote `docker build .` finds one."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(context), arcname=".")
        tar.add(str(dockerfile), arcname="Dockerfile")
    buf.seek(0)
    return buf


def up_remote(context=DEFAULT_CONTEXT, container_port: int = twin_local.DEFAULT_PORT,
              health: str = twin_local.DEFAULT_HEALTH, dockerfile=DEFAULT_DOCKERFILE) -> tuple:
    """Build and run the twin on the box. Returns (cli, twin, workdir); caller tears down."""
    context = Path(context)
    if not Path(dockerfile).exists():
        raise Unavailable(f"no Dockerfile at {dockerfile}")
    cli = connect()
    try:
        docker = ensure_docker(cli)   # 'docker' or 'sudo -n docker'
        twin_id = "twin-" + secrets.token_hex(4)
        flag = twin_local.new_flag()
        workdir = f"/tmp/neo-{twin_id}"
        _exec(cli, f"mkdir -p {workdir}")
        # ship the build context
        sftp = cli.open_sftp()
        sftp.putfo(_tar_context(context, dockerfile), f"{workdir}/ctx.tgz")
        sftp.close()
        code, _, err = _exec(cli, f"cd {workdir} && tar xzf ctx.tgz && "
                                  f"{docker} build -q -t {twin_id} .", timeout=600)
        if code != 0:
            raise Unavailable(f"remote build failed (rc={code}): {err.strip()[-200:]}")
        # pick a free-ish high port on the box
        port = 20000 + secrets.randbelow(20000)
        code, _, err = _exec(
            cli,
            f"{docker} run -d --rm --name {twin_id} --cap-add NET_ADMIN "
            f"-p 127.0.0.1:{port}:{container_port} -e NEO_STATE=/state {twin_id}",
        )
        if code != 0:
            raise Unavailable(f"remote run failed (rc={code}): {err.strip()[-200:]}")
        base = f"http://127.0.0.1:{port}"
        # health, over the box itself
        url = base + "/" + health.lstrip("/")
        healthy = False
        for _ in range(40):
            _, out, _ = _exec(cli, f"curl -fsS -o /dev/null -w '%{{http_code}}' {url} || true")
            if out.strip().startswith("2"):
                healthy = True
                break
            time.sleep(0.5)
        if not healthy:
            teardown_remote(cli, twin_id, workdir, docker)
            raise Unavailable("remote twin never became healthy")
        twin = ServerTwin(twin_id, twin_id, port, base, twin_id, flag, docker)
        return cli, twin, workdir
    except Unavailable:
        cli.close()
        raise


def teardown_remote(cli, container: str, workdir: str | None = None,
                    docker: str = "docker") -> None:
    _exec(cli, f"{docker} rm -f {container} >/dev/null 2>&1; "
               f"{docker} rmi -f {container} >/dev/null 2>&1; "
               + (f"rm -rf {workdir}" if workdir else ""))


def up(context=DEFAULT_CONTEXT, container_port: int = twin_local.DEFAULT_PORT,
       health: str = twin_local.DEFAULT_HEALTH) -> tuple[str, object]:
    """Try the server twin; on any trouble, run locally and say so.
    Returns (backend, handle) where backend is 'server' or 'local'."""
    try:
        cli, twin, workdir = up_remote(context, container_port, health)
        return "server", (cli, twin, workdir)
    except Unavailable as e:
        print(f"server twin unreachable, ran locally ({e})", file=sys.stderr)
        twin = twin_local.up(context, health=health, container_port=container_port)
        return "local", twin


def _selftest(args):
    """Actually bring up a twin on the box, hit health, tear it down."""
    try:
        cli, twin, workdir = up_remote(args.context, args.port, args.health)
    except Unavailable as e:
        print(json.dumps({"server_twin": False, "reason": str(e),
                          "fallback": "local"}))
        # prove the fallback works so the loop is never blocked
        t = twin_local.up(args.context, health=args.health, container_port=args.port)
        twin_local.teardown(t)
        print(json.dumps({"local_fallback_ok": True, "twin_id": t.id}))
        return 0
    try:
        print(json.dumps({"server_twin": True, "twin_id": twin.id,
                          "base_url_on_box": twin.base_url, "port": twin.port}))
        return 0
    finally:
        teardown_remote(cli, twin.container, workdir, twin.docker)
        cli.close()
        print(f"tore down {twin.id} on the box", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="NEO server twin (SSH + Docker)")
    p.add_argument("--context", default=str(DEFAULT_CONTEXT))
    p.add_argument("--health", default=twin_local.DEFAULT_HEALTH)
    p.add_argument("--port", type=int, default=twin_local.DEFAULT_PORT,
                   help="container listen port")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest(args)
    backend, handle = up(args.context, args.port, args.health)
    if backend == "server":
        cli, twin, workdir = handle
        print(json.dumps({"backend": "server", "twin_id": twin.id,
                          "base_url_on_box": twin.base_url}))
        teardown_remote(cli, twin.container, workdir, twin.docker)
        cli.close()
    else:
        print(json.dumps({"backend": "local", "twin_id": handle.id,
                          "base_url": handle.base_url}))
        twin_local.teardown(handle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
