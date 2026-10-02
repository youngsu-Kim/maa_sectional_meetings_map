import csv

from src.nodes.build_map import build_map_node, term_label, term_of

FALL_RECORD = {
    "row_id": "row-7",
    "meeting_index": 0,
    "section": "IOWA",
    "date": "November 13-14, 2026",
    "location": "Creighton University, Omaha, NB",
    "speakers": "Jane Doe",
    "section_url": "https://www.iowa.maa.org/",
    "latitude": 41.2651,
    "longitude": -95.9353,
    "status": "ok",
    "note": "",
}

SPRING_RECORD = {
    "row_id": "row-7",
    "meeting_index": 1,
    "section": "IOWA",
    "date": "April 3, 2027",
    "location": "Drake University, Des Moines, IA",
    "speakers": "John Doe",
    "section_url": "https://www.iowa.maa.org/",
    "latitude": 41.6089,
    "longitude": -93.7247,
    "status": "ok",
    "note": "",
}


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


def test_term_classification():
    assert term_of("November 13-14, 2026") == "fall"
    assert term_of("Fall 2026") == "fall"
    assert term_of("Dec. 4, 2026") == "fall"
    assert term_of("Oct. 30–31, 2026") == "fall"
    assert term_of("Sept. 12, 2026") == "fall"
    assert term_of("April 3, 2027") == "spring"
    assert term_of("March 27-28, 2026") == "spring"
    assert term_of("Feb 27, 2027") == "spring"
    assert term_of("Apr. 24–25, 2026") == "spring"
    assert term_of("2026 Meeting Dates To Be Announced") == ""
    assert term_label("November 13-14, 2026") == "Fall 2026"
    assert term_label("April 3, 2027") == "Spring 2027"
    assert term_label("Dec. 4, 2026") == "Fall 2026"


def test_fall_and_spring_pins_get_different_colors(tmp_path):
    html, csv_rows = _run(tmp_path, [dict(FALL_RECORD), dict(SPRING_RECORD)])
    # each color appears in the marker icon AND the legend
    assert html.count("orange") >= 2  # fall pin
    assert html.count("green") >= 2  # spring pin
    assert "Fall 2026" in html and "Spring 2027" in html  # popup labels
    # CSV: one row per meeting with its term
    assert [r["term"] for r in csv_rows] == ["fall", "spring"]
    assert [r["meeting_index"] for r in csv_rows] == ["0", "1"]


def test_map_fits_to_markers_not_default_view(tmp_path):
    html, _ = _run(tmp_path, [dict(FALL_RECORD), dict(SPRING_RECORD)])
    assert "fitBounds" in html  # auto-framed on the pins; no Canada/Mexico padding


def test_note_rendered_in_popup_and_csv(tmp_path):
    note = "geocoded as 'Creighton University, Omaha, NE' (MAA page typo: NB is New Brunswick; Nebraska is NE)"
    html, csv_rows = _run(tmp_path, [dict(FALL_RECORD, note=note)])

    assert "Omaha, NE" in html  # note visible in the marker popup
    assert "Omaha, NB" in html  # original location text preserved
    assert csv_rows[0]["note"] == note
    assert csv_rows[0]["status"] == "ok"


def test_no_note_renders_clean_popup(tmp_path):
    html, csv_rows = _run(tmp_path, [dict(FALL_RECORD)])
    assert "geocoded as" not in html
    assert csv_rows[0]["note"] == ""


def test_invalid_row_listed_in_side_note(tmp_path):
    html, csv_rows = _run(
        tmp_path,
        [
            dict(FALL_RECORD),
            dict(SPRING_RECORD, latitude=None, longitude=None, status="invalid", note=""),
        ],
    )
    assert "No location on map" in html
    assert "extraction failed" in html
    assert csv_rows[1]["status"] == "invalid"


def test_legend_present(tmp_path):
    html, _ = _run(tmp_path, [dict(FALL_RECORD)])
    assert "Fall meeting" in html
    assert "Spring meeting" in html
