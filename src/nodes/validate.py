import re

from src.config import MAX_EXTRACTION_RETRIES
from src.schemas import SectionMeetings
from src.state import PipelineState

_HTML_RE = re.compile(r"</?[a-zA-Z][^>]*>|&[a-zA-Z]+;|&#\d+;")
_URL_RE = re.compile(r"https?://", re.IGNORECASE)

FIELD_MAX_CHARS = 300


def is_tba(date: str) -> bool:
    return bool(date.strip()) and "to be announced" in date.strip().casefold()


def _has_repetition(text: str, window: int = 40, threshold: int = 3) -> bool:
    """Detect degenerate LLM repetition, independent of the repeat period.

    Probes how often the leading window of text recurs (non-overlapping).
    Runaway loops fill the whole field with one repeated unit, so the very
    start of the text is part of the pattern.
    """
    if len(text) < window * threshold:
        return False
    return text.count(text[:window]) >= threshold


def merge_meetings(sections: list[SectionMeetings]) -> dict[str, SectionMeetings]:
    """Last write wins, so retry attempts replace failed first attempts."""
    merged: dict[str, SectionMeetings] = {}
    for section in sections:
        merged[section.row_id] = section
    return merged


def validate_section(section: SectionMeetings, expected_section: str) -> list[str]:
    errors: list[str] = []

    if section.section.startswith("EXTRACTION_ERROR"):
        errors.append(section.section)
    elif section.section.strip().casefold() != expected_section.strip().casefold():
        errors.append(f"section must be exactly {expected_section!r}, got {section.section!r}")

    if _HTML_RE.search(section.section):
        errors.append(f"section contains raw HTML: {section.section[:80]!r}")

    if section.section_url and not re.match(r"^https?://", section.section_url.strip()):
        errors.append(
            f"section_url must start with http:// or https://, got {section.section_url!r}"
        )

    if not section.meetings:
        errors.append("meetings list is empty; every section must list at least one meeting")

    # Free-text fields must be clean, brief, and URL-free (section_url is the
    # only field allowed to carry a link).
    for index, meeting in enumerate(section.meetings, start=1):
        prefix = f"meeting {index}: " if len(section.meetings) > 1 else ""
        for field in ("date", "location", "speakers"):
            value = getattr(meeting, field)
            if _HTML_RE.search(value):
                errors.append(f"{prefix}{field} contains raw HTML: {value[:80]!r}")
            if _URL_RE.search(value):
                errors.append(f"{prefix}{field} must not contain URLs; links belong in section_url")
            if "learn more" in value.casefold():
                errors.append(f"{prefix}{field} must not contain 'Learn more' boilerplate")
            if len(value) > FIELD_MAX_CHARS:
                errors.append(
                    f"{prefix}{field} too long ({len(value)} chars); keep under {FIELD_MAX_CHARS}"
                )
            if _has_repetition(value):
                errors.append(f"{prefix}{field} contains repeated content")

        if is_tba(meeting.date) and (meeting.location.strip() or meeting.speakers.strip()):
            errors.append(
                f"{prefix}date is To-Be-Announced but location/speakers are populated; "
                "they must be empty"
            )

    return errors


def validate_node(state: PipelineState) -> dict:
    expected = {r["row_id"]: r["section_name"] for r in state["raw_sections"]}
    merged = merge_meetings(state["meetings"])
    attempts = state.get("retry_counts", {})

    errors: dict[str, list[str]] = {}
    failed: list[str] = []

    for row_id, section in merged.items():
        row_errors = validate_section(section, expected.get(row_id, ""))
        if row_id not in expected:
            row_errors.append(f"unknown row_id {row_id!r}")
        if row_errors:
            errors[row_id] = row_errors
            if attempts.get(row_id, 0) > MAX_EXTRACTION_RETRIES:
                failed.append(row_id)

    for row_id in expected:
        if row_id not in merged:
            errors[row_id] = ["no extraction result was returned for this row"]
            if attempts.get(row_id, 0) > MAX_EXTRACTION_RETRIES:
                failed.append(row_id)

    return {"merged": merged, "row_errors": errors, "failed_rows": failed}


def rows_needing_retry(state: PipelineState) -> list[str]:
    return [
        row_id
        for row_id in state["row_errors"]
        if state.get("retry_counts", {}).get(row_id, 0) <= MAX_EXTRACTION_RETRIES
    ]
