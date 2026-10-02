import csv
from datetime import date

from meeting_time import normalize_date
from src.nodes.build_map import (
    build_map_node,
    current_term_label,
    meeting_status,
    term_label,
    term_of,
)

TODAY = date(2026, 10, 2)  # pinned: inside the Fall 2026 term

PAST_RECORD = {
    "row_id": "row-5",
    "meeting_index": 0,
    "section": "INDIANA",
    "date": "March 27-28, 2026",
    "location": "Taylor University, IN",
    "speakers": "Jane Doe",
    "section_url": "https://www.indiana.maa.org/",
    "latitude": 40.4560812,
    "longitude": -85.5011884,
    "status": "ok",
    "note": "",
}

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
            "today": TODAY.isoformat(),
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
    assert term_of("August 4-7, 2027") == "fall"  # MathFest dates
    assert term_of("July 10, 2027") == "fall"
    assert term_of("April 3, 2027") == "spring"
    assert term_of("March 27-28, 2026") == "spring"
    assert term_of("Feb 27, 2027") == "spring"
    assert term_of("Apr. 24–25, 2026") == "spring"
    assert term_of("2026 Meeting Dates To Be Announced") == ""
    assert term_label("November 13-14, 2026") == "Fall 2026"
    assert term_label("April 3, 2027") == "Spring 2027"
    assert term_label("Dec. 4, 2026") == "Fall 2026"
    assert term_label("August 4-7, 2027") == "Fall 2027"


def test_meeting_status_buckets():
    assert meeting_status("March 27-28, 2026", TODAY) == "past"
    assert meeting_status("November 13-14, 2026", TODAY) == "current"
    assert meeting_status("Dec. 4, 2026", TODAY) == "current"
    assert meeting_status("October 30–31, 2026", TODAY) == "current"
    assert meeting_status("April 3, 2027", TODAY) == "upcoming"
    assert meeting_status("Feb 27, 2027", TODAY) == "upcoming"
    assert meeting_status("unparseable", TODAY) == "current"
    # buckets shift with time...
    jan_2027 = date(2027, 1, 15)
    assert meeting_status("November 13-14, 2026", jan_2027) == "past"
    assert meeting_status("April 3, 2027", jan_2027) == "current"
    assert meeting_status("Oct 2, 2027", jan_2027) == "upcoming"
    # summer counts toward the upcoming fall term
    jul_2027 = date(2027, 7, 10)
    assert meeting_status("Sept 10, 2027", jul_2027) == "current"
    assert meeting_status("April 3, 2027", jul_2027) == "past"


def test_current_term_label():
    assert current_term_label(TODAY) == "Fall 2026"
    assert current_term_label(date(2027, 3, 1)) == "Spring 2027"
    assert current_term_label(date(2027, 7, 1)) == "Fall 2027"


def test_past_current_upcoming_pins_get_distinct_colors(tmp_path):
    html, csv_rows = _run(
        tmp_path, [dict(PAST_RECORD), dict(FALL_RECORD), dict(SPRING_RECORD)]
    )
    # each color appears in the marker icon AND the legend
    assert html.count("lightgray") >= 2  # past pin
    assert html.count("orange") >= 2  # current-term pin
    assert html.count("green") >= 2  # upcoming pin
    # popup term labels still rendered
    assert "Fall 2026" in html and "Spring 2027" in html
    # CSV: one row per meeting with term and temporal bucket
    assert [r["term"] for r in csv_rows] == ["spring", "fall", "spring"]
    assert [r["meeting_status"] for r in csv_rows] == ["past", "current", "upcoming"]


def test_normalize_date_abbreviates_months():
    assert normalize_date("March 27-28, 2026") == "Mar 27-28, 2026"
    assert normalize_date("November 13-14, 2026") == "Nov 13-14, 2026"
    assert normalize_date("Feb. 20-21, 2026") == "Feb 20-21, 2026"
    assert normalize_date("Sept. 12, 2026") == "Sep 12, 2026"
    assert normalize_date("2026 Meeting Dates To Be Announced") == "2026 Meeting Dates To Be Announced"


def test_popup_dates_are_abbreviated(tmp_path):
    html, _ = _run(tmp_path, [dict(PAST_RECORD)])
    assert "Mar 27-28, 2026" in html
    assert "March 27-28, 2026" not in html


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
    assert "Past" in html
    assert "Current term (Fall 2026)" in html
    assert "Upcoming" in html


def test_links_to_shinylive_app(tmp_path):
    html, _ = _run(tmp_path, [dict(FALL_RECORD)])
    assert 'href="shinylive/"' in html
