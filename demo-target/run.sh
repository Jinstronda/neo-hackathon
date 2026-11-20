#!/bin/sh
# Build and run one disposable SnapVault twin for manual poking. The engine uses
# infra/twin_local instead; this is for building/exercising the target by hand.
#   ./run.sh            build + run on 127.0.0.1:8000, random flag
#   ./run.sh 8081       build + run on 127.0.0.1:8081
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
PORT="${1:-8000}"
FLAG="NEO{$(python3 -c 'import secrets;print(secrets.token_hex(8))')}"

echo "[run] building neo-demo-target ..."
docker build -q -t neo-demo-target "$HERE" >/dev/null

echo "[run] starting twin on 127.0.0.1:$PORT (flag $FLAG)"
# NET_ADMIN lets entrypoint.sh alias 169.254.169.254 for the SSRF scenario.
docker rm -f neo-demo-target-run >/dev/null 2>&1 || true
docker run -d --rm --name neo-demo-target-run \
  --cap-add=NET_ADMIN \
  -p "127.0.0.1:$PORT:8000" \
  -e "DEMO_FLAG=$FLAG" \
  neo-demo-target >/dev/null

echo "[run] waiting for health ..."
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    echo "[run] up: http://127.0.0.1:$PORT  (stop: docker rm -f neo-demo-target-run)"
    exit 0
  fi
  sleep 0.5
done
echo "[run] never became healthy" >&2
docker logs neo-demo-target-run >&2 || true
exit 1
