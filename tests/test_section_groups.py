"""Guard for data/section_groups.csv, the region headers in the app filters.

The apps degrade gracefully (unknown sections fall back to "Other"), so this
test is not a crash guard but a curation gate: it fails CI when MAA adds,
removes, or renames a section, so the new name gets an explicit region
instead of silently piling into "Other". Fix: update data/section_groups.csv.
"""
import csv

from src.config import MEETINGS_CSV_PATH, SECTION_GROUPS_PATH

ALLOWED_REGIONS = {"Northeast", "Midwest", "South", "West", "National", "Other"}


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_groups_and_data_cover_each_other():
    grouped = {row["section"] for row in _read(SECTION_GROUPS_PATH)}
    scraped = {row["section"] for row in _read(MEETINGS_CSV_PATH)}
    assert grouped == scraped, (
        f"un-grouped sections: {sorted(scraped - grouped)}; "
        f"stale group entries: {sorted(grouped - scraped)}"
    )


def test_regions_are_known():
    rows = _read(SECTION_GROUPS_PATH)
    unknown = {row["region"] for row in rows} - ALLOWED_REGIONS
    assert not unknown, f"regions outside the expected set: {sorted(unknown)}"


def test_national_rows_are_grouped_as_national():
    rows = _read(SECTION_GROUPS_PATH)
    data_rows = _read(MEETINGS_CSV_PATH)
    national_sections = {
        r["section"] for r in data_rows if r["row_id"].startswith("national-")
    }
    region_by_section = {r["section"]: r["region"] for r in rows}
    assert national_sections == {"MAA MathFest"}
    assert all(region_by_section[s] == "National" for s in national_sections)
