import csv
import html
from pathlib import Path

import folium

from src.config import MAP_PATH, MEETINGS_CSV_PATH
from src.state import PipelineState

MAP_CENTER = (39.5, -98.35)
ZOOM_START = 4

_NOTE_STYLE = (
    "position: fixed; bottom: 20px; left: 20px; z-index: 9999; "
    "background: rgba(255, 255, 255, 0.92); padding: 10px 12px; "
    "border: 1px solid #999; border-radius: 4px; font-size: 12px; "
    "max-width: 300px; max-height: 40vh; overflow-y: auto; line-height: 1.5;"
)


def build_map_node(state: PipelineState) -> dict:
    rows = state.get("geocoded", [])
    map_path = Path(state.get("map_path_out") or MAP_PATH)
    csv_path = Path(state.get("csv_path_out") or MEETINGS_CSV_PATH)

    m = folium.Map(location=list(MAP_CENTER), zoom_start=ZOOM_START, tiles="OpenStreetMap")

    placed, unplaced = [], []
    for row in rows:
        if row.get("status") == "ok" and row.get("latitude") is not None:
            popup = (
                f"<b>{html.escape(row['section'])}</b><br>"
                f"{html.escape(str(row['date']))}<br>"
                f"{html.escape(str(row['location']))}<br>"
                f"{html.escape(str(row['speakers']))}<br>"
                f"<a href='{html.escape(row['section_url'])}' "
                f"target='_blank' rel='noopener noreferrer'>"
                f"{html.escape(row['section_url'])}</a>"
            )
            folium.Marker(
                [row["latitude"], row["longitude"]],
                popup=folium.Popup(popup, max_width=300),
            ).add_to(m)
            placed.append(row)
        else:
            unplaced.append(row)

    if unplaced:
        lines = []
        for row in unplaced:
            label = html.escape(row["section"])
            if row.get("status") != "ok":
                label += " (extraction failed)"
            lines.append(label)
        note = folium.Element(
            f'<div style="{_NOTE_STYLE}">'
            f"<b>No location on map</b><br>{'<br>'.join(lines)}</div>"
        )
        m.get_root().html.add_child(note)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["row_id", "section", "date", "location", "speakers",
             "section_url", "latitude", "longitude", "status"]
        )
        for row in rows:
            writer.writerow(
                [row["row_id"], row["section"], row["date"], row["location"],
                 row["speakers"], row["section_url"],
                 row["latitude"], row["longitude"], row["status"]]
            )

    map_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(map_path))

    return {"map_path": str(map_path), "csv_path": str(csv_path)}
