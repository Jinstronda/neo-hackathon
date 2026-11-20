"""Tiny stdlib HTTP helpers shared by the reference exploits and the tests.
No third-party deps so the exploits run inside a bare twin."""
import json
import urllib.request


def _do(url, data=None, headers=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    h = {"Content-Type": "application/json"} if data is not None else {}
    h.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except ValueError:
            return e.code, None


def post(url, data, headers=None):
    return _do(url, data=data, headers=headers, method="POST")


def get(url, headers=None):
    return _do(url, headers=headers, method="GET")
