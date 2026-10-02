import csv

from conftest import (
    FIXTURE_HTML,
    SEED_CACHE,
    ScriptedFakeLLM,
    golden_meeting,
    run_graph,
)
from src.schemas import SectionMeeting


def test_happy_path_full_graph(tmp_path):
    from src.nodes import extract as extract_mod

    # start from the seed cache so cache hits are exercised
    cache_path = tmp_path / "geocode_cache.csv"
    cache_path.write_text(SEED_CACHE.read_text(encoding="utf-8"), encoding="utf-8")
    before = cache_path.read_text(encoding="utf-8")

    fake = ScriptedFakeLLM()
    extract_mod.set_llm_factory(lambda: fake)
    try:
        from src.graph import build_graph

        state = build_graph().invoke(
            {
                "dry_run": True,
                "fixture_path": str(FIXTURE_HTML),
                "limit": 0,
                "cache_path": str(cache_path),
                "map_path_out": str(tmp_path / "index.html"),
                "csv_path_out": str(tmp_path / "meetings.csv"),
            },
            config={"max_concurrency": 2},
        )
    finally:
        extract_mod.set_llm_factory(None)

    assert len(state["raw_sections"]) == 29
    assert len(state["merged"]) == 29
    assert state["row_errors"] == {}
    assert state["failed_rows"] == []

    # 7 golden locations match the seed cache; row-10 (Lafayette) and
    # row-23 (Lawrence NY) are deliberately unseeded (suspect original coords)
    assert state["cache_hits"] == 7
    assert state["cache_misses"] == 2
    assert state["cache_failures"] == 0

    # dry-run never writes to the cache
    assert cache_path.read_text(encoding="utf-8") == before

    # outputs exist
    map_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "openstreetmap" in map_html
    assert "No location on map" in map_html

    with open(tmp_path / "meetings.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 29
    assert all(r["status"] == "ok" for r in rows)
    wvu = next(r for r in rows if r["row_id"] == "row-0")
    assert float(wvu["latitude"]) == 39.6348398


def test_retry_recovers_row_after_two_failures(tmp_path):
    bad = golden_meeting("row-0").model_copy(update={"section": "WRONG SECTION"})
    fake = ScriptedFakeLLM(failures={"0": [bad, bad]})
    state = run_graph(fake, tmp_path, limit=3)

    # row-0 needed 3 attempts (2 failures + 1 success)
    assert fake.call_counts["0"] == 3
    assert state["retry_counts"]["row-0"] == 3
    assert state["merged"]["row-0"].section == "ALLEGHENY MOUNTAIN"
    assert state["row_errors"] == {}
    assert state["failed_rows"] == []


def test_permanent_failure_is_isolated(tmp_path):
    bad = SectionMeeting(
        row_id="row-1", section="EASTERN PA & DELAWARE", location="<b>oops</b>"
    )
    fake = ScriptedFakeLLM(failures={"1": [bad, bad, bad]})
    state = run_graph(fake, tmp_path, limit=3)

    assert state["retry_counts"]["row-1"] == 3
    assert state["failed_rows"] == ["row-1"]
    assert "row-1" in state["row_errors"]

    # the failed row is reported, marked invalid, and kept out of the map markers
    by_id = {r["row_id"]: r for r in state["geocoded"]}
    assert by_id["row-1"]["status"] == "invalid"
    assert by_id["row-1"]["latitude"] is None
    assert by_id["row-0"]["status"] == "ok"

    map_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "extraction failed" in map_html


def test_limit_restricts_sections(tmp_path):
    state = run_graph(ScriptedFakeLLM(), tmp_path, limit=3)
    assert len(state["raw_sections"]) == 3
    assert len(state["merged"]) == 3
