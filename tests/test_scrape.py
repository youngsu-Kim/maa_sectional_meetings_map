import pytest
from langgraph.types import Send

from src.nodes.scrape import (
    parse_national_event_cards,
    parse_national_event_page,
    parse_sections,
    scrape_node,
)
from src.schemas import Meeting, SectionMeetings

from conftest import FIXTURE_HTML, FIXTURE_HTML_WP, ROOT

FIXTURE_NATIONAL_EVENTS = ROOT / "tests" / "fixtures" / "national_events.html"
FIXTURE_NATIONAL_MATHFEST = ROOT / "tests" / "fixtures" / "national_mathfest.html"


def test_parses_all_29_sections():
    sections = parse_sections(FIXTURE_HTML.read_text(encoding="utf-8"))
    assert len(sections) == 29
    assert sections[0]["row_id"] == "row-0"
    assert sections[0]["section_name"] == "ALLEGHENY MOUNTAIN"
    assert sections[-1]["row_id"] == "row-28"
    assert sections[-1]["section_name"] == "WISCONSIN"


def test_wordpress_layout_parses():
    """The 2026 WordPress redesign: one wp-block-column per section."""
    sections = parse_sections(FIXTURE_HTML_WP.read_text(encoding="utf-8"))
    assert len(sections) == 29
    assert sections[0]["row_id"] == "row-0"
    assert sections[0]["section_name"] == "ALLEGHENY MOUNTAIN"
    assert sections[-1]["section_name"] == "WISCONSIN"
    # content excludes the heading and keeps the meeting paragraphs + link
    assert "Spring 2026" in sections[0]["content_html"]
    assert "ALLEGHENY MOUNTAIN" not in sections[0]["content_html"]
    assert "https://www.alleghenymtn.maa.org/" in sections[0]["content_html"]


def test_sections_have_html_content():
    sections = parse_sections(FIXTURE_HTML.read_text(encoding="utf-8"))
    for section in sections:
        assert section["row_id"]
        assert section["section_name"]
        assert "<" in section["content_html"]


def test_structurally_changed_page_raises():
    with pytest.raises(RuntimeError):
        parse_sections("<html><body><p>nothing here</p></body></html>")


def test_scrape_node_limit():
    state = scrape_node({"dry_run": True, "fixture_path": str(FIXTURE_HTML), "limit": 3})
    assert len(state["raw_sections"]) == 3


def test_scrape_node_no_limit():
    state = scrape_node({"dry_run": True, "fixture_path": str(FIXTURE_HTML), "limit": 0})
    assert len(state["raw_sections"]) == 29


def test_national_event_cards_filters_to_meetings():
    cards = parse_national_event_cards(
        FIXTURE_NATIONAL_EVENTS.read_text(encoding="utf-8")
    )
    # only /event/ pages count as meetings; /resource/ links are excluded
    assert cards == [("MAA MathFest", "https://maa.org/event/mathfest/")]


def test_national_event_page_parses_upcoming_list():
    name, meetings, content_html = parse_national_event_page(
        FIXTURE_NATIONAL_MATHFEST.read_text(encoding="utf-8")
    )
    assert name == "MAA MathFest"
    assert meetings == [
        ("August 4-7, 2027", "New Orleans, LA"),
        ("August 2-5, 2028", "San Diego, CA"),
        ("August 8-11, 2029", "Chicago, IL"),
        ("August 7-10, 2030", "New York, NY"),
    ]
    # compact retry content stays small and mentions the key facts
    assert "New Orleans" in content_html and len(content_html) < 5000


def test_fanout_skips_preextracted_national_rows():
    from src.graph import route_after_scrape

    raw_sections = [
        {"row_id": "row-0", "section_name": "ALLEGHENY MOUNTAIN", "content_html": ""},
        {"row_id": "national-0", "section_name": "MAA MathFest", "content_html": ""},
    ]
    sends = route_after_scrape(
        {
            "raw_sections": raw_sections,
            "meetings": [
                SectionMeetings(
                    row_id="national-0",
                    section="MAA MathFest",
                    meetings=[Meeting(date="August 4-7, 2027", location="New Orleans, LA")],
                )
            ],
        }
    )
    assert [s.arg["raw"]["row_id"] for s in sends] == ["row-0"]
    assert all(isinstance(s, Send) for s in sends)
