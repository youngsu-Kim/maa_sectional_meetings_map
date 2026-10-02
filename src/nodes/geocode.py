import csv
from pathlib import Path

from src.config import GEOCODE_CACHE_PATH, LOCATION_CORRECTIONS_PATH, USER_AGENT
from src.state import PipelineState


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

    cache = load_cache(cache_path)
    geocoder = None
    hits = misses = failures = 0
    applied: list[str] = []
    results: list[dict] = []

    for row_id, meeting in merged.items():
        record: dict = {"row_id": row_id, **meeting.model_dump()}

        if row_id in errors:
            record.update(latitude=None, longitude=None, status="invalid", note="")
            results.append(record)
            continue

        record["status"] = "ok"
        location = meeting.location.strip()

        if not location:
            # TBA rows have no location: never geocode, never guess.
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
                    found = geocoder(lookup)
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
