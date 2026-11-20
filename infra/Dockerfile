# Twin image for the SnapVault demo target. Lives in infra/ so demo-target/
# stays untouched; build with: docker build -f infra/Dockerfile demo-target
# The entrypoint aliases the link-local metadata IP onto lo so the SSRF chain
# is reachable only from inside the twin (needs --cap-add NET_ADMIN; if the cap
# is missing the app falls back to 127.0.0.1:9253 and only the SSRF scenario
# degrades).
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends iproute2 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV NEO_WEB_HOST=0.0.0.0 \
    NEO_WEB_PORT=8080 \
    NEO_META_HOST=169.254.169.254 \
    NEO_META_PORT=80 \
    NEO_STATE=/state

RUN printf '#!/bin/sh\nip addr add 169.254.169.254/32 dev lo 2>/dev/null || true\nexec python app.py\n' \
      > /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8080
CMD ["/entrypoint.sh"]
