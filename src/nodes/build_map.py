import csv
import html
import re
from datetime import date
from pathlib import Path

import folium

from src.config import MAP_PATH, MEETINGS_CSV_PATH
from src.state import PipelineState

MAP_CENTER = (39.5, -98.35)
ZOOM_START = 5  # tight on the continental US; no Canada/Mexico padding

# Full or abbreviated month names ("Feb.", "Oct", "September", ...).
_MONTHS_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"(20\d{2})")
_MONTH_NUMBERS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

TERM_COLORS = {"fall": "orange", "spring": "green"}
STATUS_COLORS = {"past": "lightgray", "current": "orange", "upcoming": "green"}

_NOTE_STYLE = (
    "position: fixed; bottom: 20px; left: 20px; z-index: 9999; "
    "background: rgba(255, 255, 255, 0.92); padding: 10px 12px; "
    "border: 1px solid #999; border-radius: 4px; font-size: 12px; "
    "max-width: 300px; max-height: 40vh; overflow-y: auto; line-height: 1.5;"
)
_LEGEND_STYLE = (
    "position: fixed; top: 20px; right: 20px; z-index: 9999; "
    "background: rgba(255, 255, 255, 0.92); padding: 8px 12px; "
    "border: 1px solid #999; border-radius: 4px; font-size: 12px; line-height: 1.8;"
)


def term_of(date: str) -> str:
    """Classify a meeting date as 'fall' or 'spring' (empty if undeterminable)."""
    months = {m[:3].casefold() for m in _MONTHS_RE.findall(date)}
    if months & {"sep", "oct", "nov", "dec"}:
        return "fall"
    if months & {"jan", "feb", "mar", "apr", "may", "jun"}:
        return "spring"
    text = date.casefold()
    if "fall" in text:
        return "fall"
    if "spring" in text:
        return "spring"
    return ""


def term_label(date: str) -> str:
    """Human label like 'Fall 2026'; falls back to the raw date text."""
    term = term_of(date)
    if not term:
        return date
    year = _YEAR_RE.search(date)
    return f"{term.capitalize()} {year.group(1)}" if year else term.capitalize()


def _parse_month_year(date_str: str):
    months = _MONTHS_RE.findall(date_str)
    year = _YEAR_RE.search(date_str)
    if not months or not year:
        return None
    return int(year.group(1)), _MONTH_NUMBERS[months[0][:3].casefold()]


def _term_key(year: int, month: int) -> tuple[int, int]:
    """Academic-year ordering: Fall 2026 < Spring 2027 < Fall 2027 < ..."""
    if month <= 6:
        return (year - 1, 1)  # spring belongs to the academic year that started prior fall
    return (year, 0)  # fall (July-Aug meetings count toward the upcoming fall term)


def current_term_label(today: date | None = None) -> str:
    today = today or date.today()
    if today.month <= 6:
        return f"Spring {today.year}"
    return f"Fall {today.year}"


def meeting_status(date_str: str, today: date | None = None) -> str:
    """Bucket a meeting as 'past', 'current', or 'upcoming' relative to today.

    Term-granular: a meeting stays 'current' for the whole academic term it
    belongs to (Fall = Jul-Dec, Spring = Jan-Jun) once that term arrives, so
    the buckets shift automatically as time passes.
    """
    today = today or date.today()
    parsed = _parse_month_year(date_str)
    if parsed is None:
        return "current"  # unparseable dates stay visible under the current bucket
    year, month = parsed

    if (year, month) < (today.year, today.month):
        return "past"

    meeting_key = _term_key(year, month)
    today_key = _term_key(today.year, today.month)
    if meeting_key < today_key:
        return "past"
    if meeting_key == today_key:
        return "current"
    return "upcoming"


def _popup(row) -> str:
    note_line = ""
    if row.get("note"):
        note_line = f"<i>{html.escape(str(row['note']))}</i><br>"
    return (
        f"<b>{html.escape(row['section'])}</b> "
        f"({html.escape(term_label(str(row['date'])))})<br>"
        f"{html.escape(str(row['date']))}<br>"
        f"{html.escape(str(row['location']))}<br>"
        f"{note_line}"
        f"{html.escape(str(row['speakers']))}<br>"
        f"<a href='{html.escape(row['section_url'])}' "
        f"target='_blank' rel='noopener noreferrer'>"
        f"{html.escape(row['section_url'])}</a>"
    )


def build_map_node(state: PipelineState) -> dict:
    rows = state.get("geocoded", [])
    map_path = Path(state.get("map_path_out") or MAP_PATH)
    csv_path = Path(state.get("csv_path_out") or MEETINGS_CSV_PATH)

    today = state.get("today")
    if isinstance(today, str):
        today = date.fromisoformat(today)
    # classify once per meeting; buckets shift automatically as time passes
    statuses = {id(r): meeting_status(str(r["date"]), today) for r in rows}

    m = folium.Map(location=list(MAP_CENTER), zoom_start=ZOOM_START, tiles="OpenStreetMap")

    placed, unplaced = [], []
    for row in rows:
        if row.get("status") == "ok" and row.get("latitude") is not None:
            color = STATUS_COLORS[statuses[id(row)]]
            folium.Marker(
                [row["latitude"], row["longitude"]],
                popup=folium.Popup(_popup(row), max_width=300),
                icon=folium.Icon(color=color),
            ).add_to(m)
            placed.append(row)
        else:
            unplaced.append(row)

    # Frame exactly the placed markers: no wasted Canada/Mexico coverage.
    if len(placed) >= 2:
        m.fit_bounds(
            [
                [min(r["latitude"] for r in placed), min(r["longitude"] for r in placed)],
                [max(r["latitude"] for r in placed), max(r["longitude"] for r in placed)],
            ]
        )
    elif len(placed) == 1:
        only = placed[0]
        m.location = [only["latitude"], only["longitude"]]
        m.options["zoom"] = 10

    if unplaced:
        lines = []
        for row in unplaced:
            label = html.escape(row["section"])
            if row.get("status") != "ok":
                label += " (extraction failed)"
            elif row.get("date"):
                label += f" ({html.escape(str(row['date']))})"
            lines.append(label)
        m.get_root().html.add_child(
            folium.Element(
                f'<div style="{_NOTE_STYLE}">'
                f"<b>No location on map</b><br>{'<br>'.join(lines)}</div>"
            )
        )

    legend = (
        '<b>Meetings</b><br>'
        '<span style="color:lightgray;">&#9679;</span> Past&nbsp;&nbsp;'
        f'<span style="color:orange;">&#9679;</span> '
        f'Current term ({current_term_label(today)})&nbsp;&nbsp;'
        '<span style="color:green;">&#9679;</span> Upcoming'
    )
    m.get_root().html.add_child(
        folium.Element(f'<div style="{_LEGEND_STYLE}">{legend}</div>')
    )

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["row_id", "meeting_index", "term", "meeting_status", "section",
             "date", "location", "speakers", "section_url", "latitude",
             "longitude", "status", "note"]
        )
        for row in rows:
            writer.writerow(
                [row["row_id"], row.get("meeting_index", 0),
                 term_of(str(row["date"])), statuses[id(row)], row["section"],
                 row["date"], row["location"], row["speakers"], row["section_url"],
                 row["latitude"], row["longitude"], row["status"],
                 row.get("note", "")]
            )

    map_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(map_path))

    return {"map_path": str(map_path), "csv_path": str(csv_path)}
