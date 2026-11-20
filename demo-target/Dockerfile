# SnapVault demo target. Deliberately vulnerable; runs only on a disposable twin.
FROM python:3.12-slim

# iproute2 gives `ip`, used by entrypoint.sh to alias the link-local metadata
# address onto loopback so the SSRF scenario reaches a real 169.254.169.254.
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# twin_local boots with -p 127.0.0.1:<rand>:8000 and probes /healthz.
ENV NEO_WEB_HOST=0.0.0.0 \
    NEO_WEB_PORT=8000 \
    NEO_META_HOST=169.254.169.254 \
    NEO_META_PORT=80 \
    NEO_STATE=/state
EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
