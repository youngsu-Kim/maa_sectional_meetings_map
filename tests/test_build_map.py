import csv
from datetime import date

from meeting_time import (
    NATIONAL_RAMP,
    PAST_ALPHA,
    UPCOMING_RAMP,
    fade_alphas,
    normalize_date,
)
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
    note = (
        "corrected from 'Creighton University, Omaha, NB' "
        "(MAA page typo: NB is New Brunswick; Nebraska is NE)"
    )
    html, csv_rows = _run(
        tmp_path,
        [dict(FALL_RECORD, location="Creighton University, Omaha, NE", note=note)],
    )

    assert "Omaha, NE" in html  # corrected location text
    assert "&dagger;" in html  # dagger marker before the note
    assert "Omaha, NB" in html  # original preserved inside the note
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


MATHFEST_RECORD = {
    "row_id": "national-0",
    "meeting_index": 0,
    "section": "MAA MathFest",
    "date": "August 4-7, 2027",
    "location": "New Orleans, LA",
    "speakers": "",
    "section_url": "https://maa.org/event/mathfest/",
    "latitude": 29.9561422,
    "longitude": -90.0733934,
    "status": "ok",
    "note": "",
}


def test_national_rows_get_own_color_and_legend(tmp_path):
    html, _ = _run(tmp_path, [dict(MATHFEST_RECORD), dict(FALL_RECORD)])
    # MathFest pins are darkpurple even though the date is 'upcoming'
    assert "darkpurple" in html
    assert "MathFest" in html  # legend entry


def test_no_mathfest_legend_without_national_rows(tmp_path):
    html, _ = _run(tmp_path, [dict(FALL_RECORD)])
    assert "MathFest" not in html


def test_fade_alphas_soonest_full_then_lighter():
    alphas = fade_alphas(["April 3, 2027", "February 10, 2027", "March 1, 2027"])
    # input order preserved: Feb is soonest -> 1.0; Mar -> 0.85; Apr -> 0.75
    assert alphas == [0.75, 1.0, 0.85]


def test_fade_alphas_national_ramp_is_steeper_than_upcoming():
    alphas = fade_alphas(
        ["August 8-11, 2029", "August 4-7, 2027", "August 7-10, 2030",
         "August 2-5, 2028"],
        NATIONAL_RAMP,
    )
    # soonest MathFest solid, then the requested 0.70 / 0.55 / 0.45 tail
    assert alphas == [0.55, 1.0, 0.45, 0.70]
    # past pins stay strictly below every future pin, so they never blend in
    assert min(UPCOMING_RAMP) > PAST_ALPHA
    assert min(NATIONAL_RAMP) > PAST_ALPHA


def test_fade_alphas_ties_share_alpha_and_ramp_tail():
    # same month ties share rank; ranks past the ramp end keep the last value
    dates = ["January 5, 2027", "January 20, 2027", "February 1, 2027",
             "March 1, 2027", "April 1, 2027", "May 1, 2027", "June 1, 2027",
             "July 1, 2027", "August 1, 2027"]
    alphas = fade_alphas(dates)
    assert alphas[0] == alphas[1] == 1.0
    assert alphas[2] == 0.85
    assert min(alphas) == 0.65


def test_past_pins_use_constant_opacity(tmp_path):
    past = [
        dict(SPRING_RECORD, row_id="row-p1", meeting_index=0,
             section="OLD A", date="April 3, 2026"),
        dict(SPRING_RECORD, row_id="row-p2", meeting_index=0,
             section="OLD B", date="May 3, 2026"),
    ]
    html, _ = _run(tmp_path, past)
    # every past pin shares the constant dimmed opacity, regardless of rank
    assert html.count('"opacity": 0.4') >= 2


def test_upcoming_and_national_pins_fade_by_date(tmp_path):
    upcoming_records = [
        dict(SPRING_RECORD, row_id="row-a", meeting_index=0,
             section="AAA", date="April 3, 2027"),
        dict(SPRING_RECORD, row_id="row-b", meeting_index=0,
             section="BBB", date="February 10, 2027"),
    ]
    mathfest_records = [
        dict(MATHFEST_RECORD, meeting_index=0, date="August 4-7, 2027"),
        dict(MATHFEST_RECORD, meeting_index=1, date="August 2-5, 2028"),
        dict(MATHFEST_RECORD, meeting_index=2, date="August 8-11, 2029"),
    ]
    html, _ = _run(
        tmp_path,
        [dict(FALL_RECORD)] + upcoming_records + mathfest_records,
    )
    # current-term pin (Nov 2026) stays opaque; fades apply per future group
    assert '"opacity": 0.85' in html or "opacity&#39;: 0.85" in html or "0.85" in html
    assert '"opacity": 0.7' in html or "opacity&#39;: 0.7" in html or "0.7" in html
    # MathFest sequence: 1.0 / 0.7 / 0.55 (soonest unmarked = fully opaque)
    assert "0.55" in html  # third MathFest
