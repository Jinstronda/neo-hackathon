#!/usr/bin/env python3
"""Exploit radar: SBOM the demo target, match it against the three feeds that
answer "what dropped and are we exposed", rank the matches, and hand the top one
to the red swarm.

  SBOM     Syft over demo-target (falls back to parsing requirements.txt).
  CISA KEV known-exploited catalog + a staged entry so the demo always matches.
  EPSS     first.org probability a CVE is exploited in the wild (30-day).
  OSV      osv.dev advisories for the exact package+version.

Rank: in KEV first, then by EPSS, then "reachable" (a direct dependency). A CVE
is not a finding — this is a worklist. Proof comes later, when the exploit fires
on the twin and dies on the patch.

Methodology: neo/skills/cve-intake/SKILL.md (radar is read-only and never
contacts a target; the triage gates and local-repro rules gate adoption into a
run). Feeds the red swarm, which scores every finding through
neo/skills/adversary-review/SKILL.md.

stdlib only; every call goes out read-only, nothing touches a target.
"""
import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "demo-target"
STAGED_KEV = Path(__file__).resolve().parent / "fixtures" / "kev_staged.json"

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://api.first.org/data/v1/epss?cve={cve}"
OSV_URL = "https://api.osv.dev/v1/query"


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "neo-radar"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _post_json(url, body, timeout=15):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "neo-radar"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ----------------------------------------------------------------------- SBOM

def build_sbom(target=TARGET):
    """[{name, version, ecosystem, direct}]. Syft if present, else requirements.txt."""
    comps = _syft_sbom(target)
    if comps:
        return comps
    print("[radar] syft unavailable or empty; parsing requirements.txt", file=sys.stderr)
    return _requirements_sbom(target)


def _syft_sbom(target):
    try:
        out = subprocess.run(["syft", f"dir:{target}", "-o", "syft-json", "-q"],
                             capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    try:
        doc = json.loads(out.stdout)
    except json.JSONDecodeError:
        return []
    direct = {n.lower() for n, _ in _requirements_pins(target)}
    comps = []
    for a in doc.get("artifacts", []):
        name = a.get("name", "")
        comps.append({
            "name": name,
            "version": a.get("version", ""),
            "ecosystem": _osv_ecosystem(a.get("type", "")),
            "direct": name.lower() in direct,
        })
    return comps


def _requirements_pins(target):
    path = Path(target) / "requirements.txt"
    pins = []
    if not path.exists():
        return pins
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "==" not in line:
            continue
        name, version = line.split("==", 1)
        pins.append((name.strip(), version.strip()))
    return pins


def _requirements_sbom(target):
    return [{"name": n, "version": v, "ecosystem": "PyPI", "direct": True}
            for n, v in _requirements_pins(target)]


def _osv_ecosystem(syft_type):
    return {"python": "PyPI", "npm": "npm", "gem": "RubyGems",
            "go-module": "Go"}.get(syft_type, "PyPI")


# ----------------------------------------------------------------------- feeds

def load_kev():
    """Set of CVE ids in the live CISA KEV feed, merged with the staged entry."""
    ids, source = set(), "staged-only"
    try:
        live = _get_json(KEV_URL, timeout=20)
        ids = {v["cveID"] for v in live.get("vulnerabilities", [])}
        source = f"live({len(ids)})+staged"
    except (urllib.error.URLError, OSError, KeyError) as e:
        print(f"[radar] live KEV unavailable ({e}); using staged only", file=sys.stderr)
    if STAGED_KEV.exists():
        staged = json.loads(STAGED_KEV.read_text())
        ids |= {v["cveID"] for v in staged.get("vulnerabilities", [])}
    return ids, source


def osv_vulns(comp):
    """OSV advisory ids for one component+version."""
    try:
        res = _post_json(OSV_URL, {
            "package": {"name": comp["name"], "ecosystem": comp["ecosystem"]},
            "version": comp["version"]})
    except (urllib.error.URLError, OSError):
        return []
    out = []
    for v in res.get("vulns", []):
        aliases = v.get("aliases", [])
        cve = next((a for a in aliases if a.startswith("CVE-")), None)
        out.append({"id": v.get("id"), "cve": cve,
                    "summary": (v.get("summary") or "")[:160]})
    return out


def epss(cve):
    if not cve:
        return 0.0
    try:
        res = _get_json(EPSS_URL.format(cve=cve), timeout=10)
    except (urllib.error.URLError, OSError):
        return 0.0
    data = res.get("data") or []
    return float(data[0]["epss"]) if data else 0.0


# ----------------------------------------------------------------------- match

def scan(target=TARGET):
    sbom = build_sbom(target)
    kev_ids, kev_source = load_kev()
    matches, seen = [], {}
    for comp in sbom:
        for adv in osv_vulns(comp):
            cve = adv["cve"]
            # one row per package+CVE; collect every OSV id that maps to it
            key = (comp["name"].lower(), comp["version"], cve or adv["id"])
            if key in seen:
                seen[key]["osv"].append(adv["id"])
                continue
            row = {
                "package": comp["name"],
                "version": comp["version"],
                "ecosystem": comp["ecosystem"],
                "cve": cve,
                "osv": [adv["id"]],
                "summary": adv["summary"],
                "kev": bool(cve and cve in kev_ids),
                "epss": round(epss(cve), 5),
                "reachable": comp["direct"],
            }
            seen[key] = row
            matches.append(row)
    # rank: in-KEV first, then EPSS, then reachable
    matches.sort(key=lambda m: (m["kev"], m["epss"], m["reachable"]), reverse=True)
    return {"sbom_size": len(sbom), "kev_source": kev_source, "matches": matches}


def main(argv=None):
    p = argparse.ArgumentParser(description="NEO exploit radar")
    p.add_argument("--target", default=str(TARGET))
    p.add_argument("--json", action="store_true", help="machine-readable output only")
    p.add_argument("--run-dir", default=None,
                   help="append a radar_match event for the top hit to this run's journal")
    args = p.parse_args(argv)

    result = scan(Path(args.target))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"SBOM: {result['sbom_size']} components   KEV: {result['kev_source']}")
        print(f"{'KEV':>3} {'EPSS':>7}  {'reach':>5}  {'package':<12} {'version':<8} {'CVE':<16} OSV")
        for m in result["matches"]:
            print(f"{'yes' if m['kev'] else ' no':>3} {m['epss']:>7.3f}  "
                  f"{'yes' if m['reachable'] else ' no':>5}  {m['package']:<12} "
                  f"{m['version']:<8} {(m['cve'] or '-'):<16} {','.join(m['osv'])}")
        top = result["matches"][0] if result["matches"] else None
        if top:
            print(f"\ntop match -> red swarm: {top['package']} {top['version']} "
                  f"{top['cve']} (kev={top['kev']} epss={top['epss']})")

    if args.run_dir and result["matches"]:
        from .journal import Journal
        top = result["matches"][0]
        Journal(args.run_dir).emit("radar_match", cve=top["cve"], kev=top["kev"],
                                   epss=top["epss"], osv=top["osv"], package=top["package"],
                                   version=top["version"], reachable=top["reachable"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
