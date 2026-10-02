"""Guards for the Shinylive export (shinylive_app/)."""

import filecmp
from pathlib import Path

from conftest import ROOT

SHINYLIVE_APP = ROOT / "shinylive_app"


def test_meeting_time_copy_is_in_sync():
    """shinylive_app/meeting_time.py must byte-match the repo-root original."""
    original = ROOT / "meeting_time.py"
    vendored = SHINYLIVE_APP / "meeting_time.py"
    assert vendored.exists(), "shinylive_app/meeting_time.py is missing"
    assert filecmp.cmp(original, vendored, shallow=False), (
        "shinylive_app/meeting_time.py is out of sync with meeting_time.py; "
        "re-copy it after changing the time-classification logic"
    )


def test_shinylive_data_snapshot_exists():
    data = SHINYLIVE_APP / "data" / "meetings_latest.csv"
    assert data.exists(), "shinylive_app/data snapshot is missing"
    lines = data.read_text(encoding="utf-8").splitlines()
    assert len(lines) > 2  # header + at least one meeting
