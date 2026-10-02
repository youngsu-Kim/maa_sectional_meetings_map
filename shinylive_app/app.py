"""Browser-only version of the MAA sectional meeting map (Shinylive/Pyodide).

Runs entirely in the visitor's browser via Pyodide - no server, deployable
on GitHub Pages. The data is a snapshot from the last pipeline run
(shinylive_app/data/meetings_latest.csv). meeting_time.py is a synced copy
of the repo-root meeting_time.py (a test enforces the sync).

Regenerate the static export with:

    .venv/bin/python -c "from shinylive._export import export; \\
        export('shinylive_app', 'site/shinylive')"
"""

from pathlib import Path

import folium
import pandas as pd
from shiny import App, reactive, render, ui

from meeting_time import current_term_label, meeting_status, term_label

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
    return m


app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.h3("MAA Sectional Meetings"),
        ui.p(
            "One pin per meeting. Buckets are relative to today, so colors ",
            "shift as terms pass. This app runs entirely in your browser.",
        ),
        ui.input_checkbox_group(
            "buckets",
            "Show meetings",
            choices=STATUS_LABELS,
            selected=list(STATUS_LABELS),
        ),
        ui.input_text("search", "Filter by section or location", ""),
        ui.output_ui("legend"),
        width="280px",
    ),
    ui.layout_column_wrap(
        ui.card(
            ui.card_header("Map"),
            ui.output_ui("map"),
            style="height: 600px;",
        ),
    ),
    ui.card(
        ui.card_header("Meetings"),
        ui.output_data_frame("table"),
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
    def legend():
        return ui.TagList(
            ui.hr(),
            ui.p(
                {"style": "font-size: 0.9em;"},
                *[
                    ui.tags.span(
                        "\u25cf ",
                        style=f"color: {STATUS_COLORS[b]}; font-weight: bold;",
                    )
                    for b in STATUS_LABELS
                ],
                " ",
                " / ".join(
                    f"{STATUS_LABELS['current']} ({current_term_label()})"
                    if b == "current"
                    else STATUS_LABELS[b]
                    for b in STATUS_LABELS
                ),
            ),
        )

    @render.ui
    def map():
        # get_root().render() is the full standalone document (scripts included);
        # an iframe srcdoc lets those scripts run and isolates Leaflet from
        # Bootstrap. (_repr_html_() returns a nested embed wrapper instead.)
        return ui.tags.iframe(
            srcdoc=build_map(filtered()).get_root().render(),
            style="width: 100%; height: 100%; border: none;",
        )

    @render.data_frame
    def table():
        view = filtered()
        columns = ["section", "date", "location", "speakers", "bucket"]
        renamed = {
            "section": "Section",
            "date": "Date",
            "location": "Location",
            "speakers": "Speakers",
            "bucket": "When",
        }
        return render.DataGrid(view[columns].rename(columns=renamed), width="100%")


app = App(app_ui, server)
