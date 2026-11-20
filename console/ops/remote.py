"""Run one shell command on the organizer box. Creds from neo-hackathon/.env, never printed."""
import os, sys, paramiko
env = dict(l.strip().split("=", 1) for l in open(os.path.expanduser("~/Documents/homodeus/projects/neo-hackathon/.env")) if "=" in l and not l.startswith("#"))
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(env["TWIN_SSH_HOST"], username=env["TWIN_SSH_USER"], password=env["TWIN_SSH_PASS"], timeout=10)
_, out, err = c.exec_command(sys.argv[1], timeout=float(os.environ.get("T", "120")))
sys.stdout.write(out.read().decode()); sys.stderr.write(err.read().decode()); sys.exit(out.channel.recv_exit_status())
