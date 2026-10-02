from src.nodes.validate import (
    is_tba,
    merge_meetings,
    validate_node,
    validate_section,
)
from src.schemas import Meeting

from conftest import golden_section, load_golden, with_meeting


def test_golden_meetings_pass_validation():
    assert validate_section(golden_section("row-0"), "ALLEGHENY MOUNTAIN") == []


def test_tba_row_passes_with_empty_fields():
    section = golden_section("row-2")  # FLORIDA, TBA, empty location/speakers
    assert validate_section(section, "FLORIDA") == []
    assert is_tba(section.meetings[0].date)


def test_section_mismatch_fails():
    section = golden_section("row-0").model_copy(update={"section": "WRONG"})
    errors = validate_section(section, "ALLEGHENY MOUNTAIN")
    assert any("section must be exactly" in e for e in errors)


def test_raw_html_fails():
    section = with_meeting(golden_section("row-0"), location="West Virginia <b>University</b>")
    errors = validate_section(section, "ALLEGHENY MOUNTAIN")
    assert any("raw HTML" in e for e in errors)


def test_bad_url_fails():
    section = golden_section("row-0").model_copy(
        update={"section_url": "alleghenymtn.maa.org"}
    )
    errors = validate_section(section, "ALLEGHENY MOUNTAIN")
    assert any("section_url" in e for e in errors)


def test_tba_with_location_fails():
    section = with_meeting(golden_section("row-2"), location="Some University")
    errors = validate_section(section, "FLORIDA")
    assert any("To-Be-Announced" in e for e in errors)


def test_extraction_error_section_fails():
    section = golden_section("row-0").model_copy(
        update={"section": "EXTRACTION_ERROR: boom()"}
    )
    errors = validate_section(section, "ALLEGHENY MOUNTAIN")
    assert any("EXTRACTION_ERROR" in e for e in errors)


def test_field_with_url_fails():
    section = with_meeting(
        golden_section("row-0"),
        location="See https://www.alleghenymtn.maa.org/ for details",
    )
    errors = validate_section(section, "ALLEGHENY MOUNTAIN")
    assert any("must not contain URLs" in e for e in errors)


def test_field_with_learn_more_boilerplate_fails():
    section = with_meeting(
        golden_section("row-0"),
        speakers="Kathryn Kozak. Learn more information here.",
    )
    errors = validate_section(section, "ALLEGHENY MOUNTAIN")
    assert any("Learn more" in e for e in errors)


def test_field_too_long_fails():
    section = with_meeting(golden_section("row-0"), location="University " * 100)
    errors = validate_section(section, "ALLEGHENY MOUNTAIN")
    assert any("too long" in e for e in errors)


def test_field_degenerate_repetition_fails():
    section = with_meeting(
        golden_section("row-0"), speakers="Della Dumbaugh, Candice Price, " * 30
    )
    errors = validate_section(section, "ALLEGHENY MOUNTAIN")
    assert any("repeated content" in e for e in errors)


def test_empty_meetings_list_fails():
    section = golden_section("row-0").model_copy(update={"meetings": []})
    errors = validate_section(section, "ALLEGHENY MOUNTAIN")
    assert any("meetings list is empty" in e for e in errors)


def test_two_meeting_section_validates():
    section = golden_section("row-0").model_copy(
        update={
            "meetings": [
                Meeting(date="October 18, 2026", location="A University, WV",
                        speakers="Jane Doe"),
                Meeting(date="April 3, 2027", location="B University, WV",
                        speakers="John Doe"),
            ]
        }
    )
    assert validate_section(section, "ALLEGHENY MOUNTAIN") == []


def test_two_meeting_section_error_is_indexed():
    section = golden_section("row-0").model_copy(
        update={
            "meetings": [
                Meeting(date="October 18, 2026", location="A University, WV",
                        speakers="Jane Doe"),
                Meeting(date="April 3, 2027", location="B University, WV",
                        speakers="Learn more here."),
            ]
        }
    )
    errors = validate_section(section, "ALLEGHENY MOUNTAIN")
    assert any(e.startswith("meeting 2:") for e in errors)


def test_merge_last_write_wins():
    first = with_meeting(golden_section("row-0"), location="first")
    second = golden_section("row-0")
    merged = merge_meetings([first, second])
    assert merged["row-0"].meetings[0].location == "West Virginia University"


def test_validate_node_marks_failed_after_retries_exhausted():
    good = golden_section("row-0")
    bad = golden_section("row-1").model_copy(update={"section": "WRONG"})
    raw_sections = [
        {"row_id": "row-0", "section_name": "ALLEGHENY MOUNTAIN", "content_html": ""},
        {"row_id": "row-1", "section_name": "EASTERN PA & DELAWARE", "content_html": ""},
    ]
    result = validate_node(
        {
            "raw_sections": raw_sections,
            "meetings": [good, bad],
            "retry_counts": {"row-0": 1, "row-1": 3},
        }
    )
    assert result["row_errors"].keys() == {"row-1"}
    assert result["failed_rows"] == ["row-1"]


def test_validate_node_flags_missing_extraction():
    raw_sections = [
        {"row_id": "row-0", "section_name": "ALLEGHENY MOUNTAIN", "content_html": ""},
    ]
    result = validate_node({"raw_sections": raw_sections, "meetings": [], "retry_counts": {}})
    assert result["row_errors"]["row-0"] == ["no extraction result was returned for this row"]


def test_golden_sections_all_validate():
    golden = load_golden()
    for key, row in golden.items():
        section = golden_section(key)
        assert validate_section(section, row["Section"]) == [], f"row {key} failed"
