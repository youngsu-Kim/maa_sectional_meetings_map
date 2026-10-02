import csv
import html
from datetime import date
from pathlib import Path

import folium

from meeting_time import (
    current_term_label,
    fade_alphas,
    meeting_status,
    normalize_date,
    term_label,
    term_of,
)
from src.config import MAP_PATH, MEETINGS_CSV_PATH
from src.state import PipelineState

MAP_CENTER = (39.5, -98.35)
ZOOM_START = 5  # tight on the continental US; no Canada/Mexico padding

TERM_COLORS = {"fall": "orange", "spring": "green"}
STATUS_COLORS = {"past": "lightgray", "current": "orange", "upcoming": "green"}
NATIONAL_COLOR = "darkpurple"  # national meetings (MathFest) get their own pin color

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
_LINK_STYLE = (
    "position: fixed; top: 20px; left: 20px; z-index: 9999; "
    "background: rgba(255, 255, 255, 0.92); padding: 8px 12px; "
    "border: 1px solid #999; border-radius: 4px; font-size: 13px;"
)


def _popup(row) -> str:
    note_line = ""
    if row.get("note"):
        note_line = f"<i>&dagger; {html.escape(str(row['note']))}</i><br>"
    return (
        f"<b>{html.escape(row['section'])}</b> "
        f"({html.escape(term_label(str(row['date'])))})<br>"
        f"{html.escape(normalize_date(str(row['date'])))}<br>"
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

    # Future pins fade with temporal distance: the soonest upcoming (and the
    # soonest national) meeting stays fully opaque, later ones get lighter.
    def _fade_group(group: list[dict]) -> dict[int, float]:
        alphas = fade_alphas([str(r["date"]) for r in group])
        return {id(r): a for r, a in zip(group, alphas)}

    upcoming_rows = [
        r for r in rows
        if r.get("status") == "ok" and r.get("latitude") is not None
        and statuses[id(r)] == "upcoming"
        and not str(r.get("row_id", "")).startswith("national-")
    ]
    national_rows = [
        r for r in rows
        if r.get("status") == "ok" and r.get("latitude") is not None
        and str(r.get("row_id", "")).startswith("national-")
    ]
    alphas = {**_fade_group(upcoming_rows), **_fade_group(national_rows)}

    m = folium.Map(location=list(MAP_CENTER), zoom_start=ZOOM_START, tiles="OpenStreetMap")

    placed, unplaced = [], []
    for row in rows:
        if row.get("status") == "ok" and row.get("latitude") is not None:
            if str(row.get("row_id", "")).startswith("national-"):
                color = NATIONAL_COLOR
            else:
                color = STATUS_COLORS[statuses[id(row)]]
            marker_kwargs = {}
            alpha = alphas.get(id(row))
            if alpha is not None and alpha < 1.0:
                marker_kwargs["opacity"] = alpha
            folium.Marker(
                [row["latitude"], row["longitude"]],
                popup=folium.Popup(_popup(row), max_width=300),
                icon=folium.Icon(color=color),
                **marker_kwargs,
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
                label += f" ({html.escape(normalize_date(str(row['date'])))})"
            lines.append(label)
        m.get_root().html.add_child(
            folium.Element(
                f'<div style="{_NOTE_STYLE}">'
                f"<b>No location on map</b><br>{'<br>'.join(lines)}</div>"
            )
        )

    has_national = any(
        str(r.get("row_id", "")).startswith("national-") for r in rows
    )
    legend = (
        '<b>Meetings</b><br>'
        '<span style="color:lightgray;">&#9679;</span> Past&nbsp;&nbsp;'
        f'<span style="color:orange;">&#9679;</span> '
        f'Current term ({current_term_label(today)})&nbsp;&nbsp;'
        '<span style="color:green;">&#9679;</span> Upcoming'
    )
    if has_national:
        legend += '&nbsp;&nbsp;<span style="color:darkpurple;">&#9679;</span> MathFest'
    m.get_root().html.add_child(
        folium.Element(f'<div style="{_LEGEND_STYLE}">{legend}</div>')
    )

    # Cross-link to the Shinylive app (deployed next to this map on Pages).
    m.get_root().html.add_child(
        folium.Element(
            f'<div style="{_LINK_STYLE}">'
            f'<a href="shinylive/" target="_blank" rel="noopener noreferrer">'
            f"Interactive version \u2192</a></div>"
        )
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
