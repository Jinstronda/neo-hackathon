"""Radar: the SBOM sees the outdated pin, and the staged KEV entry guarantees an
in-KEV match on demo day. The live-feed path is marked network and skips cleanly
offline (CI runs it when the feeds answer)."""
import urllib.error

import pytest

from neo import radar


def test_sbom_sees_outdated_pin():
    sbom = radar.build_sbom()
    pyyaml = [c for c in sbom if c["name"].lower() == "pyyaml"]
    assert pyyaml, f"pyyaml not in SBOM: {sbom}"
    assert pyyaml[0]["version"] == "5.3.1"
    assert pyyaml[0]["direct"] is True


def test_staged_kev_guarantees_match():
    ids, _ = radar.load_kev()
    assert "CVE-2020-14343" in ids, "staged KEV entry must keep the demo matchable"


@pytest.mark.network
def test_live_scan_ranks_kev_first():
    try:
        result = radar.scan()
    except (urllib.error.URLError, OSError) as e:
        pytest.skip(f"CVE feeds unreachable: {e}")
    assert result["matches"], "no matches (OSV may be unreachable)"
    top = result["matches"][0]
    assert top["kev"] is True
    assert top["cve"] == "CVE-2020-14343"
