"""Interactive Shiny front end for the MAA sectional meeting map.

Reads the CSV produced by the LangGraph pipeline (data/meetings_latest.csv)
and renders a Folium map plus a data table with live filters. Temporal
buckets (past / current term / upcoming) are recomputed at app start, so the
colors shift as time passes without re-running the pipeline.

Run from the repo root:

    shiny run app.py --reload
"""

import re
from datetime import date
from pathlib import Path

import folium
import pandas as pd
from shiny import App, reactive, render, ui

from meeting_time import (
    current_term_label,
    meeting_sort_key,
    meeting_status,
    normalize_date,
    term_label,
)

DATA_PATH = Path(__file__).resolve().parent / "data" / "meetings_latest.csv"
SOURCE_URL = "https://maa.org/section-meetings/"
REPO_URL = "https://github.com/youngsu-Kim/maa-sectional-meeting-map"

STATUS_COLORS = {
    "past": "lightgray",     # light grey
    "current": "orange",     # current term
    "upcoming": "green",     # upcoming terms
    "mathfest": "darkpurple",  # national meetings (MathFest)
}

STATUS_LABELS = {
    "past": "Past",
    "current": "Current term",
    "upcoming": "Upcoming",
    "mathfest": "MathFest",
}

# Speaker-program tags from the MAA page, color-coded in the table and popups.
SPEAKER_TYPE_COLORS = {
    "visitor": "#b45309",  # amber (blue read as a hyperlink)
    "polya": "#9467bd",    # purple
    "nam": "#d62728",      # red
    "awm": "#2ca02c",      # green
}
_SPEAKER_TAG_RE = re.compile(r"\(([^)]+)\)\s*$")


def _speaker_lines(speakers: str) -> list[tuple[str, str | None]]:
    """One (name, color) per speaker; color matches the program tag if any."""
    lines = []
    for part in speakers.split(","):
        part = part.strip()
        if not part:
            continue
        match = _SPEAKER_TAG_RE.search(part)
        color = SPEAKER_TYPE_COLORS.get(match.group(1).casefold()) if match else None
        lines.append((part, color))
    return lines

_LEGEND_STYLE = (
    "position: absolute; top: 10px; right: 10px; z-index: 9999; "
    "background: rgba(255, 255, 255, 0.92); padding: 6px 10px; "
    "border: 1px solid #999; border-radius: 4px; font-size: 12px; "
    "line-height: 1.8;"
)


def _bucket_choices() -> dict[str, object]:
    """Checkbox labels carrying the map pin colors: '\u25cf Past', ..."""
    labels = {}
    for bucket, text in STATUS_LABELS.items():
        if bucket == "current":
            text = f"{text} ({current_term_label()})"
        labels[bucket] = ui.HTML(
            f'<span style="color: {STATUS_COLORS[bucket]};">&#9679;</span> {text}'
        )
    return labels


def load_meetings() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df = df[(df["status"] == "ok") & df["latitude"].notna()].copy()
    df["latitude"] = df["latitude"].astype(float)
    df["longitude"] = df["longitude"].astype(float)
    # Buckets are relative to *now*, so the app stays current between runs.
    # National meetings (row_id national-*) form their own MathFest category.
    df["bucket"] = [
        "mathfest" if str(row_id).startswith("national-") else meeting_status(str(d))
        for row_id, d in zip(df["row_id"], df["date"])
    ]
    return df


def _popup_html(row) -> str:
    note = ""
    if isinstance(row["note"], str) and row["note"]:
        note = f"<i>{row['note']}</i><br>"
    speakers = "".join(
        f'<span style="color:{color};">{name}</span><br>' if color else f"{name}<br>"
        for name, color in _speaker_lines(_text(row["speakers"]))
    )
    return (
        f"<b>{row['section']}</b> ({term_label(str(row['date']))})<br>"
        f"{normalize_date(_text(row['date']))}<br>"
        f"{row['location']}<br>"
        f"{note}"
        f"{speakers}"
        f"<a href='{row['section_url']}' target='_blank' rel='noopener noreferrer'>"
        f"{row['section_url']}</a>"
    )


def build_map(view: pd.DataFrame) -> folium.Map:
    m = folium.Map(location=[39.5, -98.35], zoom_start=4, tiles="OpenStreetMap")
    for _, row in view.iterrows():
        folium.Marker(
            [row["latitude"], row["longitude"]],
            popup=folium.Popup(_popup_html(row), max_width=300),
            icon=folium.Icon(color=STATUS_COLORS[row["bucket"]]),
        ).add_to(m)
    if len(view) >= 2:
        m.fit_bounds(
            [
                [view["latitude"].min(), view["longitude"].min()],
                [view["latitude"].max(), view["longitude"].max()],
            ]
        )
    legend = (
        '<span style="color:lightgray;">&#9679;</span> Past&nbsp;&nbsp;'
        f'<span style="color:orange;">&#9679;</span> '
        f'Current term ({current_term_label()})&nbsp;&nbsp;'
        '<span style="color:green;">&#9679;</span> Upcoming&nbsp;&nbsp;'
        '<span style="color:darkpurple;">&#9679;</span> MathFest'
    )
    m.get_root().html.add_child(
        folium.Element(f'<div style="{_LEGEND_STYLE}">{legend}</div>')
    )
    return m


def _text(value) -> str:
    return "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value)


def _collected_line() -> str | None:
    """'Data collected: Oct 2, 2026' from the pipeline's last_run.txt."""
    try:
        d = date.fromisoformat(
            (DATA_PATH.parent / "last_run.txt").read_text(encoding="utf-8").strip()
        )
    except (OSError, ValueError):
        return None
    return f"Data collected: {d.strftime('%b')} {d.day}, {d.year}"


app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.h3("MAA Sectional Meetings"),
        ui.p(
            {"style": "font-size: 0.85em;"},
            ui.tags.a(
                "Data source: maa.org/section-meetings",
                href=SOURCE_URL,
                target="_blank",
                rel="noopener noreferrer",
            ),
            ui.tags.br(),
            ui.em("Unofficial extract; there may be errors."),
            *(
                [ui.tags.br(), _collected_line()]
                if _collected_line()
                else []
            ),
        ),
        ui.input_checkbox_group(
            "buckets",
            "Show meetings",
            choices=_bucket_choices(),
            selected=["current", "upcoming", "mathfest"],
        ),
        ui.input_text("search", "Filter by section or location", ""),
        ui.input_radio_buttons(
            "sortby",
            "Sort table by",
            choices={"date": "Date", "section": "Section"},
            selected="section",
            inline=True,
        ),
        ui.tags.hr(),
        ui.p(
            {"style": "font-size: 0.85em; margin-bottom: 0;"},
            "Maintained by ",
            ui.tags.a(
                "Youngsu Kim",
                href=REPO_URL,
                target="_blank",
                rel="noopener noreferrer",
            ),
        ),
        width="280px",
    ),
    ui.layout_column_wrap(
        ui.card(
            ui.output_ui("map"),
            style="height: 600px;",
        ),
    ),
    ui.card(
        ui.card_header("Meetings"),
        ui.output_ui("table"),
    ),
)


def server(input, output, session):
    df = load_meetings()

    @reactive.calc
    def filtered() -> pd.DataFrame:
        view = df[df["bucket"].isin(list(input.buckets()))]
        query = input.search().strip().casefold()
        if query:
            mask = (
                view["section"].str.casefold().str.contains(query, na=False)
                | view["location"].str.casefold().str.contains(query, na=False)
            )
            view = view[mask]
        return view

    @render.ui
    def map():
        # get_root().render() is the full standalone document (scripts included);
        # an iframe srcdoc lets those scripts run and isolates Leaflet from
        # Bootstrap. (_repr_html_() returns a nested embed wrapper instead.)
        return ui.tags.iframe(
            srcdoc=build_map(filtered()).get_root().render(),
            style="width: 100%; height: 100%; border: none;",
        )

    @render.ui
    def table():
        view = filtered().copy()
        view["__sort"] = view["date"].map(lambda d: meeting_sort_key(str(d)))
        if input.sortby() == "section":
            view = view.sort_values(["section", "__sort"])
        else:
            view = view.sort_values("__sort")
        view = view.drop(columns="__sort")

        head = ui.tags.thead(
            ui.tags.tr(
                *[ui.tags.th(h) for h in
                  ("Section", "Date", "Location", "Speakers", "When")]
            )
        )
        body = []
        for _, row in view.iterrows():
            section = _text(row["section"])
            url = _text(row["section_url"])
            section_cell = (
                ui.tags.a(section, href=url, target="_blank", rel="noopener noreferrer")
                if url.startswith("http")
                else section
            )
            bucket = _text(row["bucket"])
            speakers_cell = [
                ui.tags.div(name, style=f"color: {color};") if color else ui.tags.div(name)
                for name, color in _speaker_lines(_text(row["speakers"]))
            ]
            location_text = _text(row["location"])
            if location_text and row["latitude"] and row["longitude"]:
                location_cell = ui.tags.a(
                    location_text,
                    href=(
                        "https://www.google.com/maps/search/"
                        f"?api=1&query={row['latitude']},{row['longitude']}"
                    ),
                    target="_blank",
                    rel="noopener noreferrer",
                )
            else:
                location_cell = location_text
            body.append(
                ui.tags.tr(
                    ui.tags.td(section_cell),
                    ui.tags.td(normalize_date(_text(row["date"]))),
                    ui.tags.td(location_cell),
                    ui.tags.td(*speakers_cell),
                    ui.tags.td(
                        ui.tags.span(
                            "\u25cf",
                            style=f"color: {STATUS_COLORS.get(bucket, 'black')};",
                            title=bucket,
                        )
                    ),
                )
            )
        return ui.tags.div(
            ui.tags.table(
                head,
                ui.tags.tbody(*body),
                class_="table table-striped table-sm mb-0",
                style="font-size: 0.85em;",
            ),
            style="max-height: 420px; overflow-y: auto;",
        )


app = App(app_ui, server)
