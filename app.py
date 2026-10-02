"""Interactive Shiny front end for the MAA sectional meeting map.

Reads the CSV produced by the LangGraph pipeline (data/meetings_latest.csv)
and renders a Folium map plus a data table with live filters. Temporal
buckets (past / current term / upcoming) are recomputed at app start, so the
colors shift as time passes without re-running the pipeline.

Run from the repo root:

    shiny run app.py --reload
"""

from pathlib import Path

import folium
import pandas as pd
from shiny import App, reactive, render, ui

from meeting_time import (
    current_term_label,
    meeting_sort_key,
    meeting_status,
    term_label,
)

DATA_PATH = Path(__file__).resolve().parent / "data" / "meetings_latest.csv"

STATUS_COLORS = {
    "past": "lightgray",   # light grey
    "current": "orange",   # current term
    "upcoming": "green",   # upcoming terms
}

STATUS_LABELS = {
    "past": "Past",
    "current": "Current term",
    "upcoming": "Upcoming",
}

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
    df["bucket"] = df["date"].map(lambda d: meeting_status(str(d)))
    return df


def _popup_html(row) -> str:
    note = ""
    if isinstance(row["note"], str) and row["note"]:
        note = f"<i>{row['note']}</i><br>"
    return (
        f"<b>{row['section']}</b> ({term_label(str(row['date']))})<br>"
        f"{row['date']}<br>"
        f"{row['location']}<br>"
        f"{note}"
        f"{row['speakers']}<br>"
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
        '<span style="color:green;">&#9679;</span> Upcoming'
    )
    m.get_root().html.add_child(
        folium.Element(f'<div style="{_LEGEND_STYLE}">{legend}</div>')
    )
    return m


def _text(value) -> str:
    return "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value)


app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.h3("MAA Sectional Meetings"),
        ui.input_checkbox_group(
            "buckets",
            "Show meetings",
            choices=_bucket_choices(),
            selected=list(STATUS_LABELS),
        ),
        ui.input_text("search", "Filter by section or location", ""),
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
        view = view.sort_values("__sort").drop(columns="__sort")

        head = ui.tags.thead(
            ui.tags.tr(
                *[ui.tags.th(h) for h in
                  ("Section", "Date", "Location", "Speakers", "When", "Website")]
            )
        )
        body = []
        for _, row in view.iterrows():
            body.append(
                ui.tags.tr(
                    ui.tags.td(_text(row["section"])),
                    ui.tags.td(_text(row["date"])),
                    ui.tags.td(_text(row["location"])),
                    ui.tags.td(_text(row["speakers"])),
                    ui.tags.td(_text(row["bucket"])),
                    ui.tags.td(
                        ui.tags.a(
                            "link",
                            href=_text(row["section_url"]),
                            target="_blank",
                            rel="noopener noreferrer",
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
