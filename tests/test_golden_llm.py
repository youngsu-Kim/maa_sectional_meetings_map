"""Live-LLM golden comparison. Opt-in: set LLM_MODEL and RUN_GOLDEN_LLM=1.

Compares structured extraction against tests/fixtures/golden_meetings.csv.
Section names and URLs must match exactly; free-text field diffs are reported
so quality regressions are visible without failing on cosmetic differences.
"""

import os

import pytest

from src.fake_llm import normalize_row_id

from conftest import FIXTURE_HTML, load_golden

pytestmark = pytest.mark.skipif(
    not (os.environ.get("LLM_MODEL") and os.environ.get("RUN_GOLDEN_LLM")),
    reason="set LLM_MODEL and RUN_GOLDEN_LLM=1 to run live LLM extraction",
)


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/").casefold()


def test_extraction_matches_golden():
    from src.config import make_llm
    from src.nodes.extract import build_prompt
    from src.nodes.scrape import parse_sections
    from src.schemas import SectionMeeting

    sections = parse_sections(FIXTURE_HTML.read_text(encoding="utf-8"))
    method = os.environ.get("LLM_STRUCTURED_METHOD", "json_schema")
    llm = make_llm().with_structured_output(SectionMeeting, method=method)

    extracted = {}
    for raw in sections:
        meeting = llm.invoke(build_prompt(raw))
        extracted[normalize_row_id(meeting.row_id)] = meeting

    golden = load_golden()
    assert set(extracted) == set(golden), "row-id sets must match the golden CSV"

    structural = []
    textual = []
    for key, meeting in extracted.items():
        expected = golden[key]
        if meeting.section.casefold() != expected["Section"].casefold():
            structural.append(f"{key}: section {meeting.section!r} != {expected['Section']!r}")
        if _normalize_url(meeting.section_url) != _normalize_url(expected["SectionURL"]):
            structural.append(f"{key}: url {meeting.section_url!r} != {expected['SectionURL']!r}")
        for field in ("date", "location", "speakers"):
            got = getattr(meeting, field)
            want = expected[field.capitalize()] if field != "url" else expected["SectionURL"]
            if got.strip() != want.strip():
                textual.append(f"{key}.{field}: {got!r} != {want!r}")

    assert not structural, "structural mismatches:\n" + "\n".join(structural)
    if textual:
        print("\nFree-text field differences (informational):\n" + "\n".join(textual))
