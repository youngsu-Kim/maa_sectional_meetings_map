import csv

from src.nodes.build_map import build_map_node


def _row(**overrides):
    row = {
        "row_id": "row-7",
        "section": "IOWA",
        "date": "Fall 2026",
        "location": "Creighton University, Omaha, NB",
        "speakers": "Jane Doe",
        "section_url": "https://www.iowa.maa.org/",
        "latitude": 41.2651,
        "longitude": -95.9353,
        "status": "ok",
        "note": "",
    }
    row.update(overrides)
    return row


def _run(tmp_path, rows):
    build_map_node(
        {
            "geocoded": rows,
            "map_path_out": str(tmp_path / "index.html"),
            "csv_path_out": str(tmp_path / "meetings.csv"),
        }
    )
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    with open(tmp_path / "meetings.csv", newline="", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    return html, csv_rows


def test_note_rendered_in_popup_and_csv(tmp_path):
    note = "geocoded as 'Creighton University, Omaha, NE' (MAA page typo: NB is New Brunswick; Nebraska is NE)"
    html, csv_rows = _run(tmp_path, [_row(note=note)])

    assert "Omaha, NE" in html  # note visible in the marker popup
    assert "Omaha, NB" in html  # original location text preserved
    assert csv_rows[0]["note"] == note
    assert csv_rows[0]["status"] == "ok"


def test_no_note_renders_clean_popup(tmp_path):
    html, csv_rows = _run(tmp_path, [_row()])
    assert "geocoded as" not in html
    assert csv_rows[0]["note"] == ""


def test_invalid_row_listed_in_side_note(tmp_path):
    html, csv_rows = _run(
        tmp_path,
        [
            _row(),
            _row(row_id="row-1", section="EASTERN PA & DELAWARE",
                 latitude=None, longitude=None, status="invalid", note=""),
        ],
    )
    assert "No location on map" in html
    assert "extraction failed" in html
    assert csv_rows[1]["status"] == "invalid"
