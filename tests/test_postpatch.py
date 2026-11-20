"""Regression, post-patch: with the documented fixes applied to a copy of the
target, the same reference exploit is dead for every scenario. This is the merge
gate encoded as a test: a fixed bug can never come back silently, and FIXES.md
is proven to actually close each class."""
import _patch
import pytest
from conftest import exploit_and_check


@pytest.mark.postpatch
def test_exploit_dies_after_fix(scenario, tmp_path):
    app = _patch.write_patched(tmp_path / "patched")
    verdict = exploit_and_check(scenario, tmp_path / "state", app_path=app)
    assert verdict["objective_complete"] is False, (
        f"{scenario.name}: exploit STILL works after the fix: {verdict}")


@pytest.mark.postpatch
def test_fixes_md_anchors_match_app():
    # apply() raises if any FIXES.md anchor drifted from app.py
    assert _patch.apply(), "patched source is empty"
