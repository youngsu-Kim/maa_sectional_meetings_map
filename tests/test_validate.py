from src.nodes.validate import is_tba, merge_meetings, validate_meeting, validate_node
from src.schemas import SectionMeeting

from conftest import golden_meeting


def test_golden_meetings_pass_validation():
    meeting = golden_meeting("row-0")  # ALLEGHENY MOUNTAIN, WVU
    assert validate_meeting(meeting, "ALLEGHENY MOUNTAIN") == []


def test_tba_row_passes_with_empty_fields():
    meeting = golden_meeting("row-2")  # FLORIDA, TBA, empty location/speakers
    assert validate_meeting(meeting, "FLORIDA") == []
    assert is_tba(meeting.date)


def test_section_mismatch_fails():
    meeting = golden_meeting("row-0")
    errors = validate_meeting(meeting, "SOME OTHER SECTION")
    assert any("section must be exactly" in e for e in errors)


def test_raw_html_fails():
    meeting = golden_meeting("row-0").model_copy(
        update={"location": "West Virginia <b>University</b>"}
    )
    errors = validate_meeting(meeting, "ALLEGHENY MOUNTAIN")
    assert any("raw HTML" in e for e in errors)


def test_bad_url_fails():
    meeting = golden_meeting("row-0").model_copy(
        update={"section_url": "alleghenymtn.maa.org"}
    )
    errors = validate_meeting(meeting, "ALLEGHENY MOUNTAIN")
    assert any("section_url" in e for e in errors)


def test_tba_with_location_fails():
    meeting = golden_meeting("row-2").model_copy(update={"location": "Some University"})
    errors = validate_meeting(meeting, "FLORIDA")
    assert any("To-Be-Announced" in e for e in errors)


def test_merge_last_write_wins():
    first = golden_meeting("row-0").model_copy(update={"location": "first"})
    second = golden_meeting("row-0")
    merged = merge_meetings([first, second])
    assert merged["row-0"].location == "West Virginia University"


def test_validate_node_marks_failed_after_retries_exhausted():
    good = golden_meeting("row-0")
    bad = golden_meeting("row-1").model_copy(update={"section": "WRONG"})
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


def test_extraction_error_section_fails():
    meeting = golden_meeting("row-0").model_copy(
        update={"section": "EXTRACTION_ERROR: boom()"}
    )
    errors = validate_meeting(meeting, "ALLEGHENY MOUNTAIN")
    assert any("EXTRACTION_ERROR" in e for e in errors)


def test_field_with_url_fails():
    meeting = golden_meeting("row-0").model_copy(
        update={"location": "See https://www.alleghenymtn.maa.org/ for details"}
    )
    errors = validate_meeting(meeting, "ALLEGHENY MOUNTAIN")
    assert any("must not contain URLs" in e for e in errors)


def test_field_with_learn_more_boilerplate_fails():
    meeting = golden_meeting("row-0").model_copy(
        update={"speakers": "Kathryn Kozak. Learn more information here."}
    )
    errors = validate_meeting(meeting, "ALLEGHENY MOUNTAIN")
    assert any("Learn more" in e for e in errors)


def test_field_too_long_fails():
    meeting = golden_meeting("row-0").model_copy(update={"location": "University " * 100})
    errors = validate_meeting(meeting, "ALLEGHENY MOUNTAIN")
    assert any("too long" in e for e in errors)


def test_field_degenerate_repetition_fails():
    blob = "Della Dumbaugh, Candice Price, " * 30
    meeting = golden_meeting("row-0").model_copy(update={"speakers": blob})
    errors = validate_meeting(meeting, "ALLEGHENY MOUNTAIN")
    assert any("repeated content" in e for e in errors)
