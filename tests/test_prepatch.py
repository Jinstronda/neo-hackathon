"""Attack-replay, pre-patch: against the vulnerable target every scenario's
reference exploit lands and the server-side check fires. This is the proof the
exploit is real, and it is the regression floor — if a scenario stops being
exploitable, the demo silently lost a bug and this test says so."""
import pytest

from conftest import exploit_and_check


@pytest.mark.prepatch
def test_exploit_lands(scenario, tmp_path):
    verdict = exploit_and_check(scenario, tmp_path / "state")
    assert verdict["objective_complete"] is True, (
        f"{scenario.name}: exploit did not fire server-side: {verdict}")
    assert verdict["evidence"], f"{scenario.name}: no server-side evidence"
