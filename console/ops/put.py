"""Upload one file to the organizer box. Creds from neo-hackathon/.env, never printed."""
import os, sys, paramiko
env = dict(l.strip().split("=", 1) for l in open(os.path.expanduser("~/Documents/homodeus/projects/neo-hackathon/.env")) if "=" in l and not l.startswith("#"))
t = paramiko.Transport((env["TWIN_SSH_HOST"], 22)); t.connect(username=env["TWIN_SSH_USER"], password=env["TWIN_SSH_PASS"])
paramiko.SFTPClient.from_transport(t).put(sys.argv[1], sys.argv[2]); t.close()
