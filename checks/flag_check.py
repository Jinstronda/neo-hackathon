"""Server-side decision for the Docker retest gate (infra/replay loads this).

replay.py runs each reference exploit against a disposable twin and asks us,
not the exploit, whether the objective was met. The exploit runs in a host
process and cannot read the twin's internal event log, so the decision is
grounded in what the TARGET returned, never in the exploit's own boolean:

  sqli  the server answered role="admin"; the admin password is randomized and
        unguessable, so an admin role can only come from the injection.
  ssrf  this run's secret flag came back through the admin export; the flag is a
        server-side secret that only the full chain can surface.
  jwt   this run's secret flag came back from the admin endpoint on a token the
        server never issued.

Each exploit prints its result dict as the last `{...}` line of stdout.
"""
import ast


def _last_result(output):
    for line in reversed((output or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                val = ast.literal_eval(line)
                if isinstance(val, dict):
                    return val
            except (ValueError, SyntaxError):
                continue
    return {}


def objective_complete(flag: str, exploit_name: str, output: str) -> bool:
    r = _last_result(output)
    if "sqli" in exploit_name:
        return r.get("role") == "admin"          # server-decided role
    if "ssrf" in exploit_name or "jwt" in exploit_name:
        return bool(flag) and (flag in output or r.get("flag") == flag)
    return bool(flag) and flag in output          # default: this run's secret leaked
