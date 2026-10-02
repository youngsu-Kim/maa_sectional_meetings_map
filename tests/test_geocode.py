from pathlib import Path

from src.nodes.geocode import (
    geocode_node,
    load_cache,
    load_corrections,
    load_section_regions,
    save_cache,
)
from src.schemas import Meeting, SectionMeetings

from conftest import SEED_CACHE, golden_section, load_golden


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
        def geocode(location, **kwargs):
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
        return lambda location, **kwargs: None

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
        "src.nodes.geocode.make_geocoder", lambda: (lambda location, **kwargs: FakePlace())
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
    # the corrected text is what gets listed; the note keeps the original
    assert record["location"] == "Creighton University, Omaha, NE"
    assert record["latitude"] == 41.2651
    assert "corrected from 'Creighton University, Omaha, NB'" in record["note"]
    assert "Nebraska is NE" in record["note"]
    assert result["corrections_applied"] == [
        "row-7: Creighton University, Omaha, NB -> Creighton University, Omaha, NE"
    ]
    # cached under the corrected key so future runs hit the cache
    assert "Creighton University, Omaha, NE" in load_cache(cache_path)


def test_load_section_regions_parses_viewbox(tmp_path):
    path = tmp_path / "regions.csv"
    path.write_text(
        "section,country_codes,viewbox\n"
        'SEAWAY,"us,ca",\n'
        'METROPOLITAN NEW YORK,us,"-74.6,40.3,-71.5,41.9"\n',
        encoding="utf-8",
    )
    regions = load_section_regions(path)
    assert regions["SEAWAY"] == {"country_codes": "us,ca", "viewbox": None}
    assert regions["METROPOLITAN NEW YORK"] == {
        "country_codes": "us",
        "viewbox": ((41.9, -74.6), (40.3, -71.5)),
    }


def test_regions_file_covers_all_sections():
    """Every known MAA section must have a region entry (catches CSV typos)."""
    from src.config import SECTION_REGIONS_PATH

    regions = load_section_regions(SECTION_REGIONS_PATH)
    golden = load_golden()
    missing = [row["Section"] for row in golden.values() if row["Section"] not in regions]
    assert not missing, f"sections missing from section_regions.csv: {missing}"
    # sections spanning the border need both countries
    assert regions["SEAWAY"]["country_codes"] == "us,ca"
    assert regions["PACIFIC NORTHWEST"]["country_codes"] == "us,ca"


def _region_recorder(calls):
    def fake_geocoder():
        def geocode(location, **kwargs):
            calls.append((location, kwargs))
            return None

        return geocode

    return fake_geocoder


def test_geocode_is_region_aware(tmp_path, monkeypatch):
    """Venue lookups carry the section's country codes / viewbox."""
    from src.config import SECTION_REGIONS_PATH

    calls: list = []
    monkeypatch.setattr("src.nodes.geocode.make_geocoder", _region_recorder(calls))

    regions_path = tmp_path / "regions.csv"
    regions_path.write_text(
        "section,country_codes,viewbox\n"
        'SEAWAY,"us,ca",\n'
        'METROPOLITAN NEW YORK,us,"-74.6,40.3,-71.5,41.9"\n',
        encoding="utf-8",
    )
    seaway = SectionMeetings(
        row_id="row-23", section="SEAWAY",
        meetings=[Meeting(date="April 17, 2026", location="St. John Fisher University")],
    )
    metrony = SectionMeetings(
        row_id="row-12", section="METROPOLITAN NEW YORK",
        meetings=[Meeting(date="May 2, 2026", location="Saint Thomas Aquinas College")],
    )

    geocode_node(
        {
            "merged": {"row-23": seaway, "row-12": metrony},
            "row_errors": {},
            "dry_run": False,
            "cache_path": str(tmp_path / "cache.csv"),
            "corrections_path": str(tmp_path / "corrections.csv"),
            "regions_path": str(regions_path),
        }
    )

    by_location = {loc: kwargs for loc, kwargs in calls}
    assert by_location["St. John Fisher University"]["country_codes"] == "us,ca"
    metro_kwargs = by_location["Saint Thomas Aquinas College"]
    assert metro_kwargs["country_codes"] == "us"
    assert metro_kwargs["bounded"] is True
    assert metro_kwargs["viewbox"] == ((41.9, -74.6), (40.3, -71.5))


def test_unknown_section_falls_back_to_us(tmp_path, monkeypatch):
    calls: list = []
    monkeypatch.setattr("src.nodes.geocode.make_geocoder", _region_recorder(calls))

    unknown = SectionMeetings(
        row_id="row-99", section="SOME NEW SECTION",
        meetings=[Meeting(date="May 2, 2026", location="Some College")],
    )
    geocode_node(
        {
            "merged": {"row-99": unknown},
            "row_errors": {},
            "dry_run": False,
            "cache_path": str(tmp_path / "cache.csv"),
            "corrections_path": str(tmp_path / "corrections.csv"),
            "regions_path": str(tmp_path / "nope.csv"),
        }
    )
    assert calls and calls[0][1]["country_codes"] == "us"


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
    assert record["location"] == "Creighton University, Omaha, NE"  # corrected listing
    assert record["note"]  # the note is kept even on cache hits
