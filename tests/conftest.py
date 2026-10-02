import csv
import sys
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.fake_llm import normalize_row_id  # noqa: E402
from src.schemas import SectionMeeting  # noqa: E402

FIXTURE_HTML = ROOT / "tests" / "fixtures" / "section_meetings.html"
FIXTURE_HTML_WP = ROOT / "tests" / "fixtures" / "section_meetings_wp.html"
GOLDEN_CSV = ROOT / "tests" / "fixtures" / "golden_meetings.csv"
# Frozen 7-venue cache: tests must not depend on the live data/geocode_cache.csv,
# which grows as real runs resolve new locations.
SEED_CACHE = ROOT / "tests" / "fixtures" / "geocode_cache_seed.csv"


def load_golden() -> dict[str, dict]:
    rows = {}
    with open(GOLDEN_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows[normalize_row_id(row["row"])] = row
    return rows


def golden_meeting(key: str) -> SectionMeeting:
    row = load_golden()[normalize_row_id(key)]
    return SectionMeeting(
        row_id=f"row-{normalize_row_id(key)}",
        section=row["Section"],
        date=row["Date"],
        location=row["Location"],
        speakers=row["Speakers"],
        section_url=row["SectionURL"],
    )


class ScriptedFakeLLM:
    """Fake structured LLM: golden data by default, scripted failures first."""

    def __init__(self, failures: dict[str, list] | None = None):
        self.failures = failures or {}
        self.call_counts: dict[str, int] = defaultdict(int)

    def invoke(self, prompt: str, config=None, **kwargs) -> SectionMeeting:
        from src.fake_llm import _ROW_ID_RE

        match = _ROW_ID_RE.search(prompt)
        key = normalize_row_id(match.group(1)) if match else ""
        self.call_counts[key] += 1
        script = self.failures.get(key, [])
        if self.call_counts[key] <= len(script):
            return script[self.call_counts[key] - 1]
        return golden_meeting(key)


@pytest.fixture
def seeded_cache(tmp_path):
    cache_path = tmp_path / "geocode_cache.csv"
    cache_path.write_text(SEED_CACHE.read_text(encoding="utf-8"), encoding="utf-8")
    return cache_path


def run_graph(fake_llm, tmp_path, limit=0):
    """Invoke the full graph offline with a fake LLM; return the final state."""
    from src.graph import build_graph
    from src.nodes import extract

    extract.set_llm_factory(lambda: fake_llm)
    try:
        graph = build_graph()
        return graph.invoke(
            {
                "dry_run": True,
                "fixture_path": str(FIXTURE_HTML),
                "limit": limit,
                "cache_path": str(tmp_path / "geocode_cache.csv"),
                "corrections_path": str(tmp_path / "corrections.csv"),
                "map_path_out": str(tmp_path / "index.html"),
                "csv_path_out": str(tmp_path / "meetings.csv"),
            },
            config={"max_concurrency": 2},
        )
    finally:
        extract.set_llm_factory(None)
