from src.nodes.geocode import geocode_node, load_cache, save_cache
from src.schemas import SectionMeeting

from conftest import SEED_CACHE, golden_meeting


def test_load_seed_cache():
    cache = load_cache(SEED_CACHE)
    assert len(cache) == 7
    assert cache["West Virginia University"] == (39.6348398, -79.9542095)


def test_cache_round_trip(tmp_path):
    path = tmp_path / "cache.csv"
    save_cache(path, {"A University": (1.0, 2.0), "B University": None})
    # None coordinates are not persisted; unresolved locations retry next run.
    assert load_cache(path) == {"A University": (1.0, 2.0)}


def _state(meetings, cache_path, dry_run=True, errors=None):
    merged = {m.row_id: m for m in meetings}
    return {
        "merged": merged,
        "row_errors": errors or {},
        "dry_run": dry_run,
        "cache_path": str(cache_path),
    }


def test_dry_run_uses_cache_and_skips_network(seeded_cache):
    before = seeded_cache.read_text(encoding="utf-8")
    result = geocode_node(
        _state(
            [golden_meeting("row-0"), golden_meeting("row-2"), golden_meeting("row-10")],
            seeded_cache,
        )
    )
    # row-0: WVU is in the seed cache -> hit
    # row-2: FLORIDA has no location -> skipped, not a miss
    # row-10: University of Lafayette is unknown -> miss, but no network in dry-run
    assert result["cache_hits"] == 1
    assert result["cache_misses"] == 1
    assert result["cache_failures"] == 0
    by_id = {r["row_id"]: r for r in result["geocoded"]}
    assert by_id["row-0"]["latitude"] == 39.6348398
    assert by_id["row-2"]["latitude"] is None
    assert by_id["row-10"]["latitude"] is None
    # dry-run must not modify the cache file
    assert seeded_cache.read_text(encoding="utf-8") == before


def test_invalid_rows_get_status(seeded_cache):
    meeting = golden_meeting("row-1")
    result = geocode_node(
        _state([meeting], seeded_cache, errors={"row-1": ["some problem"]})
    )
    record = result["geocoded"][0]
    assert record["status"] == "invalid"
    assert record["latitude"] is None


def test_live_geocode_resolves_and_saves(seeded_cache, monkeypatch):
    class FakePlace:
        latitude = 30.2241
        longitude = -92.0198

    def fake_geocoder():
        def geocode(location):
            return FakePlace() if "Lafayette" in location else None

        return geocode

    monkeypatch.setattr("src.nodes.geocode.make_geocoder", fake_geocoder)

    result = geocode_node(
        _state([golden_meeting("row-10")], seeded_cache, dry_run=False)
    )
    record = result["geocoded"][0]
    assert record["latitude"] == 30.2241
    assert record["longitude"] == -92.0198
    # resolved location was written back to the cache
    cache = load_cache(seeded_cache)
    assert cache["University of Lafayette"] == (30.2241, -92.0198)


def test_live_geocode_unresolvable_counts_failure(seeded_cache, monkeypatch):
    def fake_geocoder():
        return lambda location: None

    monkeypatch.setattr("src.nodes.geocode.make_geocoder", fake_geocoder)

    result = geocode_node(
        _state([golden_meeting("row-10")], seeded_cache, dry_run=False)
    )
    assert result["cache_failures"] == 1
    assert result["geocoded"][0]["latitude"] is None
    # unresolved locations are not persisted to the cache
    assert "University of Lafayette" not in load_cache(seeded_cache)
