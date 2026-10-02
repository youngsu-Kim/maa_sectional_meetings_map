from pathlib import Path

from src.nodes.geocode import geocode_node, load_cache, load_corrections, save_cache
from src.schemas import Meeting, SectionMeetings

from conftest import SEED_CACHE, golden_section


def test_load_seed_cache():
    cache = load_cache(SEED_CACHE)
    assert len(cache) == 7
    assert cache["West Virginia University"] == (39.6348398, -79.9542095)


def test_load_corrections_missing_file(tmp_path):
    assert load_corrections(tmp_path / "nope.csv") == {}


def test_load_corrections(tmp_path):
    path = tmp_path / "corrections.csv"
    path.write_text(
        'location,corrected,reason\n'
        '"Creighton University, Omaha, NB","Creighton University, Omaha, NE",NB is New Brunswick\n',
        encoding="utf-8",
    )
    corrections = load_corrections(path)
    assert corrections["Creighton University, Omaha, NB"] == (
        "Creighton University, Omaha, NE",
        "NB is New Brunswick",
    )


def test_cache_round_trip(tmp_path):
    path = tmp_path / "cache.csv"
    save_cache(path, {"A University": (1.0, 2.0), "B University": None})
    # None coordinates are not persisted; unresolved locations retry next run.
    assert load_cache(path) == {"A University": (1.0, 2.0)}


def _state(sections, cache_path, dry_run=True, errors=None):
    merged = {s.row_id: s for s in sections}
    return {
        "merged": merged,
        "row_errors": errors or {},
        "dry_run": dry_run,
        "cache_path": str(cache_path),
        "corrections_path": str(Path(cache_path).parent / "corrections.csv"),
    }


def test_dry_run_uses_cache_and_skips_network(seeded_cache):
    before = seeded_cache.read_text(encoding="utf-8")
    result = geocode_node(
        _state(
            [golden_section("row-0"), golden_section("row-2"), golden_section("row-10")],
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


def test_each_meeting_gets_its_own_record(seeded_cache):
    section = golden_section("row-0").model_copy(
        update={
            "meetings": [
                Meeting(date="October 18, 2026", location="West Virginia University",
                        speakers="Jane Doe"),
                Meeting(date="April 3, 2027", location="Iowa State University",
                        speakers="John Doe"),
            ]
        }
    )
    result = geocode_node(_state([section], seeded_cache))
    records = result["geocoded"]
    assert len(records) == 2
    assert records[0]["meeting_index"] == 0
    assert records[1]["meeting_index"] == 1
    assert records[0]["latitude"] == 39.6348398
    assert records[1]["latitude"] == 42.0279608
    assert result["cache_hits"] == 2


def test_invalid_rows_get_status(seeded_cache):
    section = golden_section("row-1")
    result = geocode_node(
        _state([section], seeded_cache, errors={"row-1": ["some problem"]})
    )
    record = result["geocoded"][0]
    assert record["status"] == "invalid"
    assert record["latitude"] is None


def test_invalid_section_without_meetings_still_recorded(seeded_cache):
    section = SectionMeetings(row_id="row-1", section="EASTERN PA & DELAWARE", meetings=[])
    result = geocode_node(
        _state([section], seeded_cache, errors={"row-1": ["some problem"]})
    )
    record = result["geocoded"][0]
    assert record["status"] == "invalid"
    assert record["date"] == ""


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
        _state([golden_section("row-10")], seeded_cache, dry_run=False)
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
        _state([golden_section("row-10")], seeded_cache, dry_run=False)
    )
    assert result["cache_failures"] == 1
    assert result["geocoded"][0]["latitude"] is None
    # unresolved locations are not persisted to the cache
    assert "University of Lafayette" not in load_cache(seeded_cache)


def _write_corrections(tmp_path):
    path = tmp_path / "corrections.csv"
    path.write_text(
        'location,corrected,reason\n'
        '"Creighton University, Omaha, NB","Creighton University, Omaha, NE",'
        "MAA page typo: NB is New Brunswick; Nebraska is NE\n",
        encoding="utf-8",
    )
    return path


def _creighton_section():
    return SectionMeetings(
        row_id="row-7",
        section="IOWA",
        section_url="",
        meetings=[
            Meeting(
                date="Fall 2026",
                location="Creighton University, Omaha, NB",
                speakers="",
            )
        ],
    )


def test_correction_fixes_typo_and_keeps_note(tmp_path, monkeypatch):
    cache_path = tmp_path / "cache.csv"
    save_cache(cache_path, {})
    corrections_path = _write_corrections(tmp_path)

    class FakePlace:
        latitude = 41.2651
        longitude = -95.9353

    monkeypatch.setattr(
        "src.nodes.geocode.make_geocoder", lambda: (lambda location: FakePlace())
    )

    result = geocode_node(
        {
            "merged": {"row-7": _creighton_section()},
            "row_errors": {},
            "dry_run": False,
            "cache_path": str(cache_path),
            "corrections_path": str(corrections_path),
        }
    )

    record = result["geocoded"][0]
    # original text is preserved for display
    assert record["location"] == "Creighton University, Omaha, NB"
    # geocoded via the corrected string, with a visible note
    assert record["latitude"] == 41.2651
    assert "Omaha, NE" in record["note"]
    assert "Nebraska is NE" in record["note"]
    assert result["corrections_applied"] == [
        "row-7: Creighton University, Omaha, NB -> Creighton University, Omaha, NE"
    ]
    # cached under the corrected key so future runs hit the cache
    assert "Creighton University, Omaha, NE" in load_cache(cache_path)


def test_correction_hits_cache_on_second_run(tmp_path, monkeypatch):
    cache_path = tmp_path / "cache.csv"
    save_cache(cache_path, {"Creighton University, Omaha, NE": (41.2651, -95.9353)})
    corrections_path = _write_corrections(tmp_path)

    # no geocoder allowed: everything must come from the cache
    def boom():
        raise AssertionError("geocoder must not be called")

    monkeypatch.setattr("src.nodes.geocode.make_geocoder", boom)

    result = geocode_node(
        {
            "merged": {"row-7": _creighton_section()},
            "row_errors": {},
            "dry_run": False,
            "cache_path": str(cache_path),
            "corrections_path": str(corrections_path),
        }
    )
    record = result["geocoded"][0]
    assert record["latitude"] == 41.2651
    assert result["cache_hits"] == 1
    assert record["note"]  # the note is kept even on cache hits
