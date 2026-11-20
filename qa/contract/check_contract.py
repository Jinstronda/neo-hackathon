#!/usr/bin/env python3
"""Contract test between the console UI and the NEO engine.

Validates a run (from a file or a live /api/run URL) against qa/schema/run.schema.json,
then runs two semantic checks the schema alone cannot: the server-side retest gate
(pre-patch exploit works, post-patch it is dead) and UI-reads-exist (every field a
console component reads is present in what the engine served).

Stdlib only, so it runs on any machine with python3 and no install. The JSON Schema
file is the single source of truth; this just interprets the subset of keywords used.

    python3 qa/contract/check_contract.py path/to/run.json
    python3 qa/contract/check_contract.py https://host/api/run --bypass <vercel-bypass>
"""
import json
import sys
import urllib.request

HERE = __import__("pathlib").Path(__file__).resolve().parent
SCHEMA = json.loads((HERE.parent / "schema" / "run.schema.json").read_text())

# Fields each console component reads off an event, from a grep of neo-web/{components,lib,app}.
# A run the engine serves must carry every one of these, or a screen renders blank on stage.
UI_READS = {
    "radar_match": ["cve", "kev", "epss", "osv", "package", "version", "reachable"],
    "twin_create": ["twin_id", "where", "image"],
    "red_start": ["twin_id", "models"],
    "red_finding": ["finding_id", "model", "cls", "location", "request", "confirmed_by"],
    "flag_check": ["finding_id", "scenario", "phase", "objective_complete", "evidence"],
    "blue_patch": ["finding_id", "branch", "diff", "commits"],
    "review": ["reviewer", "verdict", "comment"],
    "twin_deploy": ["twin_id", "where", "finding_id"],
    "retest": ["finding_id", "objective_complete", "status"],
    "tests": ["passed", "total"],
    "merge": ["by", "approved_by"],
    "metrics": ["minutes_exploit_to_fix", "where", "regression_tests"],
    # pr_number/pr_url (only when a real PR opened), regression_added, cost_usd and the surface
    # counts are optional: sent only when measured, and every renderer hides them when absent
}


class Fail(Exception):
    pass


def validate(node, schema, path, root):
    """Minimal JSON Schema draft 2020-12 check: the keywords used in run.schema.json."""
    if "$ref" in schema:
        ref = schema["$ref"]
        assert ref.startswith("#/"), f"only local refs: {ref}"
        target = root
        for part in ref[2:].split("/"):
            target = target[part]
        return validate(node, target, path, root)

    t = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "number": (int, float), "boolean": bool}
    if t == "number" and isinstance(node, bool):
        raise Fail(f"{path}: expected number, got boolean")
    if t and not isinstance(node, types[t]):
        raise Fail(f"{path}: expected {t}, got {type(node).__name__}")

    if "const" in schema and node != schema["const"]:
        raise Fail(f"{path}: expected const {schema['const']!r}, got {node!r}")
    if "enum" in schema and node not in schema["enum"]:
        raise Fail(f"{path}: {node!r} not in {schema['enum']}")
    if "minLength" in schema and isinstance(node, str) and len(node) < schema["minLength"]:
        raise Fail(f"{path}: shorter than {schema['minLength']}")
    if "minimum" in schema and isinstance(node, (int, float)) and node < schema["minimum"]:
        raise Fail(f"{path}: below minimum {schema['minimum']}")

    if isinstance(node, dict):
        for key in schema.get("required", []):
            if key not in node:
                raise Fail(f"{path}: missing required field {key!r}")
        for key, sub in schema.get("properties", {}).items():
            if key in node:
                validate(node[key], sub, f"{path}.{key}", root)

    if isinstance(node, list):
        if "minItems" in schema and len(node) < schema["minItems"]:
            raise Fail(f"{path}: has {len(node)} items, need {schema['minItems']}")
        if "items" in schema:
            for i, item in enumerate(node):
                validate(item, schema["items"], f"{path}[{i}]", root)

    for sub in schema.get("allOf", []):
        validate(node, sub, path, root)
    if "if" in schema:
        try:
            validate(node, schema["if"], path, root)
        except Fail:
            matched = False
        else:
            matched = True
        if matched and "then" in schema:
            validate(node, schema["then"], path, root)
        if not matched and "else" in schema:
            validate(node, schema["else"], path, root)


def load(src, bypass):
    if src.startswith(("http://", "https://")):
        req = urllib.request.Request(src)
        if bypass:
            req.add_header("x-vercel-protection-bypass", bypass)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    return json.loads(open(src).read())


def check_retest_gate(events):
    """The red-to-green flip must come from server-side flag checks, not an agent claim."""
    pre = [e for e in events if e["type"] == "flag_check" and e.get("phase") == "pre-patch"]
    post = [e for e in events if e["type"] == "flag_check" and e.get("phase") == "post-patch"]
    retest = [e for e in events if e["type"] == "retest"]
    if not pre or not all(e.get("objective_complete") is True for e in pre):
        raise Fail("retest gate: no pre-patch flag_check with objective_complete=true (exploit must work before the fix)")
    post_dead = all(e.get("objective_complete") is False for e in post) if post else True
    retest_dead = all(e.get("objective_complete") is False and e.get("status") == "green" for e in retest) if retest else False
    if not (post or retest):
        raise Fail("retest gate: no post-patch flag_check or retest (exploit never re-run after the fix)")
    if post and not post_dead:
        raise Fail("retest gate: a post-patch flag_check still reports objective_complete=true (exploit not dead)")
    if retest and not retest_dead:
        raise Fail("retest gate: a retest is not green with objective_complete=false")


def check_ui_reads(events):
    seen = {}
    for e in events:
        seen.setdefault(e["type"], set()).update(e.keys())
    missing = []
    for etype, fields in UI_READS.items():
        if etype not in seen:
            continue  # absence of a whole event is a coverage gap, not a field mismatch
        for f in fields:
            if f not in seen[etype]:
                missing.append(f"{etype}.{f}")
    if missing:
        raise Fail("UI reads fields the engine did not send: " + ", ".join(missing))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    bypass = None
    if "--bypass" in sys.argv:
        bypass = sys.argv[sys.argv.index("--bypass") + 1]
    src = args[0] if args else "../../web/public/runs/fixture.json"
    data = load(src, bypass)
    results = []
    for name, fn in [
        ("schema", lambda: validate(data, SCHEMA, "run", SCHEMA)),
        ("retest-gate", lambda: check_retest_gate(data["events"])),
        ("ui-reads-exist", lambda: check_ui_reads(data["events"])),
    ]:
        try:
            fn()
            results.append((name, "PASS", ""))
        except Fail as e:
            results.append((name, "FAIL", str(e)))
    src_label = data.get("source", "n/a")
    print(f"contract check against {src}  (source={src_label}, events={len(data.get('events', []))})")
    for name, verdict, detail in results:
        print(f"  {verdict:4}  {name}" + (f"  -> {detail}" if detail else ""))
    sys.exit(1 if any(v == "FAIL" for _, v, _ in results) else 0)


if __name__ == "__main__":
    main()
