import csv
from pathlib import Path

from src.config import (
    GEOCODE_CACHE_PATH,
    LOCATION_CORRECTIONS_PATH,
    SECTION_REGIONS_PATH,
    USER_AGENT,
)
from src.schemas import Meeting
from src.state import PipelineState

# Sections not listed in section_regions.csv geocode US-only by default.
REGION_DEFAULT = {"country_codes": "us", "viewbox": None}


def load_corrections(path) -> dict[str, tuple[str, str]]:
    """Curated source-data typos: original -> (corrected, reason)."""
    corrections: dict[str, tuple[str, str]] = {}
    p = Path(path)
    if not p.exists():
        return corrections
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            original = (row.get("location") or "").strip()
            corrected = (row.get("corrected") or "").strip()
            reason = (row.get("reason") or "").strip()
            if original and corrected:
                corrections[original] = (corrected, reason)
    return corrections


def load_section_regions(path) -> dict[str, dict]:
    """Per-section geocoding regions: section -> {country_codes, viewbox}.

    Host venues are almost always inside the section's territory, so
    ambiguous venue names ("St. Thomas Aquinas College" exists on several
    continents) must be resolved within the section's region. The optional
    viewbox (min_lon, min_lat, max_lon, max_lat) adds a hard bound for
    sections where the country alone is still too wide.
    """
    regions: dict[str, dict] = {}
    p = Path(path)
    if not p.exists():
        return regions
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            section = (row.get("section") or "").strip()
            country_codes = (row.get("country_codes") or "").strip()
            if not section:
                continue
            viewbox = None
            raw_box = (row.get("viewbox") or "").strip()
            if raw_box:
                try:
                    min_lon, min_lat, max_lon, max_lat = (
                        float(v) for v in raw_box.split(",")
                    )
                    # geopy takes two opposite corners as (lat, lon) pairs.
                    viewbox = ((max_lat, min_lon), (min_lat, max_lon))
                except ValueError:
                    continue
            regions[section] = {
                "country_codes": country_codes or REGION_DEFAULT["country_codes"],
                "viewbox": viewbox,
            }
    return regions


def _geocode_kwargs(region: dict) -> dict:
    kwargs: dict = {"country_codes": region["country_codes"]}
    if region.get("viewbox"):
        kwargs["viewbox"] = region["viewbox"]
        kwargs["bounded"] = True
    return kwargs


def load_cache(path) -> dict[str, tuple[float, float]]:
    cache: dict[str, tuple[float, float]] = {}
    p = Path(path)
    if not p.exists():
        return cache
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("location") and row.get("latitude") and row.get("longitude"):
                try:
                    cache[row["location"]] = (float(row["latitude"]), float(row["longitude"]))
                except ValueError:
                    continue
    return cache


def save_cache(path, cache: dict[str, tuple[float, float] | None]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["location", "latitude", "longitude"])
        for location, coords in cache.items():
            if coords is not None:
                writer.writerow([location, coords[0], coords[1]])


def make_geocoder():
    from geopy.extra.rate_limiter import RateLimiter
    from geopy.geocoders import Nominatim

    geolocator = Nominatim(user_agent=USER_AGENT)
    return RateLimiter(geolocator.geocode, min_delay_seconds=1)


def geocode_node(state: PipelineState) -> dict:
    merged = state.get("merged", {})
    errors = state.get("row_errors", {})
    dry_run = state.get("dry_run", False)
    cache_path = state.get("cache_path", GEOCODE_CACHE_PATH)
    corrections = load_corrections(
        state.get("corrections_path", LOCATION_CORRECTIONS_PATH)
    )
    regions = load_section_regions(
        state.get("regions_path", SECTION_REGIONS_PATH)
    )

    cache = load_cache(cache_path)
    geocoder = None
    hits = misses = failures = 0
    applied: list[str] = []
    results: list[dict] = []

    for row_id, section in merged.items():
        section_invalid = row_id in errors
        region = regions.get(section.section, REGION_DEFAULT)
        # An invalid section may carry no meetings; still emit one record so
        # it shows up in the CSV and the map's side note.
        meetings = section.meetings or [Meeting()]

        for index, meeting in enumerate(meetings):
            record: dict = {
                "row_id": row_id,
                "meeting_index": index,
                "section": section.section,
                "date": meeting.date,
                "location": meeting.location,
                "speakers": meeting.speakers,
                "section_url": section.section_url,
            }

            if section_invalid:
                record.update(latitude=None, longitude=None, status="invalid", note="")
                results.append(record)
                continue

            record["status"] = "ok"
            location = meeting.location.strip()

            if not location:
                # TBA meetings have no location: never geocode, never guess.
                record.update(latitude=None, longitude=None, note="")
                results.append(record)
                continue

            # Known source-data typos: geocode the corrected string, but display
            # the original text and keep a note of what was changed and why.
            lookup, note = location, ""
            if location in corrections:
                corrected, reason = corrections[location]
                lookup = corrected
                note = f"geocoded as {corrected!r}" + (f" ({reason})" if reason else "")
                applied.append(f"{row_id}: {location} -> {corrected}")

            if lookup in cache:
                hits += 1
                record.update(latitude=cache[lookup][0], longitude=cache[lookup][1])
            else:
                misses += 1
                coords = None
                if not dry_run:
                    if geocoder is None:
                        geocoder = make_geocoder()
                    try:
                        # Region-aware: venues resolve inside the section's
                        # territory (e.g. 'St. Thomas Aquinas College' is on
                        # three continents; only one is near New York).
                        found = geocoder(lookup, **_geocode_kwargs(region))
                        if found is not None:
                            coords = (found.latitude, found.longitude)
                    except Exception:  # noqa: BLE001 - geocode failures degrade to no marker
                        coords = None
                    if coords is None:
                        failures += 1
                    cache[lookup] = coords
                    save_cache(cache_path, cache)  # incremental save: crash-safe
                record.update(latitude=coords[0] if coords else None,
                              longitude=coords[1] if coords else None)

            record["note"] = note
            results.append(record)

    return {
        "geocoded": results,
        "cache_hits": hits,
        "cache_misses": misses,
        "cache_failures": failures,
        "corrections_applied": applied,
    }
