"""Dated snapshots of the scraped data (data/archive/)."""

import csv
from datetime import date

from src.main import save_dated_snapshot


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["section", "date"])
        writer.writerows(rows)


def test_snapshot_uses_dated_filename(tmp_path):
    latest = tmp_path / "meetings_latest.csv"
    _write_csv(latest, [("IOWA", "Nov 13-14, 2026")])

    dest = save_dated_snapshot(latest, tmp_path / "archive", date(2026, 10, 2))
    assert dest == tmp_path / "archive" / "meetings_2026-10-02.csv"
    assert dest.exists()
    with open(dest, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[1] == ["IOWA", "Nov 13-14, 2026"]


def test_snapshot_same_day_overwrites(tmp_path):
    latest = tmp_path / "meetings_latest.csv"
    _write_csv(latest, [("IOWA", "Nov 13-14, 2026")])
    save_dated_snapshot(latest, tmp_path / "archive", date(2026, 10, 2))

    # a later run the same day replaces that day's snapshot
    _write_csv(latest, [("IOWA", "Nov 13-14, 2026"), ("OHIO", "Apr 2027")])
    dest = save_dated_snapshot(latest, tmp_path / "archive", date(2026, 10, 2))
    with open(dest, newline="", encoding="utf-8") as f:
        assert len(list(csv.reader(f))) == 3  # header + 2 rows
