import operator
from typing import Annotated, Any, TypedDict

from src.schemas import SectionMeeting


class RawSection(TypedDict):
    """One accordion entry from the MAA section-meetings page."""

    row_id: str
    section_name: str
    content_html: str


class ExtractTask(TypedDict):
    """Payload sent to a single extract_one invocation (via Send)."""

    raw: RawSection
    feedback: list[str]
    retry_count: int


def merge_dict(left: dict | None, right: dict | None) -> dict:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class PipelineState(TypedDict, total=False):
    # invocation inputs
    dry_run: bool
    fixture_path: str
    limit: int
    cache_path: str
    map_path_out: str
    csv_path_out: str

    # scrape
    raw_sections: list[RawSection]

    # extraction fan-out (each extract_one appends one meeting)
    meetings: Annotated[list[SectionMeeting], operator.add]
    retry_counts: Annotated[dict[str, int], merge_dict]

    # validation
    merged: dict[str, SectionMeeting]
    row_errors: dict[str, list[str]]
    failed_rows: list[str]

    # geocoding
    geocoded: list[dict[str, Any]]
    cache_hits: int
    cache_misses: int
    cache_failures: int

    # outputs
    map_path: str
    csv_path: str
