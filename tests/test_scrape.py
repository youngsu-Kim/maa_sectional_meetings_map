import pytest

from src.nodes.scrape import parse_sections, scrape_node

from conftest import FIXTURE_HTML, FIXTURE_HTML_WP


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
