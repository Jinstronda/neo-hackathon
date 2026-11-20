#!/bin/sh
# Alias the link-local cloud-metadata address onto loopback so the SSRF chain
# reaches a real 169.254.169.254 inside the twin. Needs CAP_NET_ADMIN (run the
# twin with --cap-add=NET_ADMIN). Best-effort: app.py falls back to 127.0.0.1
# if the alias or the port-80 bind is refused, so the container still boots.
ip addr add 169.254.169.254/32 dev lo 2>/dev/null || \
  echo "[entrypoint] could not alias 169.254.169.254 (need --cap-add=NET_ADMIN); metadata falls back to 127.0.0.1:9253" >&2
exec python /app/app.py
