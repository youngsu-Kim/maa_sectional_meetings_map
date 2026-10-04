"""Interactive Shiny front end for the MAA sectional meeting map.

Reads the CSV produced by the LangGraph pipeline (data/meetings_latest.csv)
and renders a Folium map plus a data table with live filters. Temporal
buckets (past / current term / upcoming) are recomputed at app start, so the
colors shift as time passes without re-running the pipeline.

Run from the repo root:

    shiny run app.py --reload
"""

import csv
import re
from datetime import date
from pathlib import Path

import folium
import pandas as pd
from shiny import App, reactive, render, ui

from meeting_time import (
    NATIONAL_RAMP,
    PAST_ALPHA,
    UPCOMING_RAMP,
    current_term_label,
    fade_alphas,
    meeting_sort_key,
    meeting_status,
    normalize_date,
    term_label,
)

DATA_PATH = Path(__file__).resolve().parent / "data" / "meetings_latest.csv"
SECTION_GROUPS_PATH = Path(__file__).resolve().parent / "data" / "section_groups.csv"
SOURCE_URL = "https://maa.org/section-meetings/"
REPO_URL = "https://github.com/youngsu-Kim/maa_sectional_meetings_map"

STATUS_COLORS = {
    "past": "lightgray",     # light grey
    "current": "orange",     # current term
    "upcoming": "green",     # upcoming terms
    "mathfest": "darkpurple",  # national meetings (MathFest)
}

STATUS_LABELS = {
    "current": "Current term",
    "upcoming": "Upcoming",
    "mathfest": "MathFest",
    "past": "Past",
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
        note = f"<i>&dagger; {row['note']}</i><br>"
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
    m = folium.Map(location=[39.5, -98.35], zoom_start=4, max_zoom=19, tiles=None)
    # Basemaps: standard OSM, plus Esri satellite imagery for street-level
    # detail when zoomed in; the switcher (bottom-right) toggles them.
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Imagery &copy; Esri",
        name="Satellite",
        max_zoom=19,
    ).add_to(m)
    # Standard last: the control's radio defaults to the last base layer.
    folium.TileLayer(tiles="OpenStreetMap", name="Standard", max_zoom=19).add_to(m)

    # Future pins fade with temporal distance: the soonest upcoming (and the
    # soonest MathFest) meeting stays fully opaque, later ones get lighter.
    # Upcoming fades gently (never as faint as past); MathFest fades steeper.
    # Past pins use a constant dimmed opacity.
    fade: dict = {}
    for bucket, ramp in (("upcoming", UPCOMING_RAMP), ("mathfest", NATIONAL_RAMP)):
        sub = view[view["bucket"] == bucket]
        alphas = fade_alphas([str(d) for d in sub["date"]], ramp)
        fade.update(zip(sub.index, alphas))
    past_idx = view.index[view["bucket"] == "past"]
    fade.update(zip(past_idx, [PAST_ALPHA] * len(past_idx)))

    for _, row in view.iterrows():
        marker_kwargs = {}
        alpha = fade.get(row.name)
        if alpha is not None and alpha < 1.0:
            marker_kwargs["opacity"] = alpha
        folium.Marker(
            [row["latitude"], row["longitude"]],
            popup=folium.Popup(_popup_html(row), max_width=300),
            icon=folium.Icon(color=STATUS_COLORS[row["bucket"]]),
            **marker_kwargs,
        ).add_to(m)
    if len(view) >= 2:
        m.fit_bounds(
            [
                [view["latitude"].min(), view["longitude"].min()],
                [view["latitude"].max(), view["longitude"].max()],
            ]
        )
    legend = (
        f'<span style="color:orange;">&#9679;</span> '
        f'Current term ({current_term_label()})&nbsp;&nbsp;'
        '<span style="color:green;">&#9679;</span> Upcoming&nbsp;&nbsp;'
        '<span style="color:darkpurple;">&#9679;</span> MathFest&nbsp;&nbsp;'
        '<span style="color:lightgray;">&#9679;</span> Past'
    )
    m.get_root().html.add_child(
        folium.Element(f'<div style="{_LEGEND_STYLE}">{legend}</div>')
    )
    folium.LayerControl(collapsed=False, position="bottomright").add_to(m)
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


_MEETINGS = load_meetings()

# Region grouping from data/section_groups.csv (MAA lists its sections
# flat; these larger regions are ours). They become the divider headers in
# the section filter, and the filter also matches region words. Sections
# absent from the CSV fall back to "Other".
def _region_map() -> dict[str, str]:
    try:
        with open(SECTION_GROUPS_PATH, newline="", encoding="utf-8") as f:
            return {row["section"]: row["region"] for row in csv.DictReader(f)}
    except OSError:
        return {}


_REGION_BY_SECTION = _region_map()
_MEETINGS["region"] = _MEETINGS["section"].map(_REGION_BY_SECTION).fillna("Other")
# Combined "Section (Region)" haystack: lets a region word filter by region.
_MEETINGS["_search"] = _MEETINGS["section"] + " (" + _MEETINGS["region"] + ")"

REGION_ORDER = ["Northeast", "Midwest", "South", "West", "National", "Other"]


def _grouped_section_choices() -> dict:
    """Optgroup choices: region divider headers with plain section names.

    A leading "Regions" divider makes each region itself selectable
    ("All of West"), mirroring what typing the region word + Enter does.
    """
    groups: dict[str, dict[str, str]] = {region: {} for region in REGION_ORDER}
    for section in sorted(_MEETINGS["section"].unique()):
        groups.setdefault(_REGION_BY_SECTION.get(section, "Other"), {})[section] = section
    choices: dict = {"All": "All"}
    region_opts = {r: f"All of {r}" for r, s in groups.items() if s and r != "Other"}
    if region_opts:
        choices["Regions"] = region_opts
    choices.update({r: s for r, s in groups.items() if s})
    return choices


_SECTION_CHOICES = _grouped_section_choices()

app_ui = ui.page_sidebar(
    ui.sidebar(
        {"style": "font-size: 0.85em;"},
        # Bootstrap sets rem-based sizes on headings and form controls, which
        # ignore the parent's em; force them to inherit the sidebar's size.
        # Keep bslib's default 24px column gap; only tighten the hr margins
        # (Bootstrap's 2rem default was the worst offender).
        ui.tags.style(
            "aside select.form-select, aside select.shiny-input-select, "
            "aside .selectize-input, aside .selectize-input input "
            "{ font-size: inherit; } "
            "aside h3 { font-size: 1.15em; font-weight: 600; line-height: 1.3; } "
            "aside hr { margin: 0.55rem 0; } "
            "aside #sortby { margin-bottom: 0.75rem; } "
            # \\vfill: pin the footer to the sidebar bottom. The aside IS
            # .sidebar; make it a flex column, let the content box fill it,
            # and the footer rides an auto top margin — pure CSS, so it
            # tracks window resizes with no JS needed.
            "aside.sidebar { display: flex; flex-direction: column; } "
            "aside .sidebar-content { flex: 1 1 auto; } "
            "aside .sidebar-content > .sidebar-footer { margin-top: auto !important; } "
            "#pane_resizer { height: 16px; flex: none; cursor: row-resize; "
            "display: flex; align-items: center; } "
            "#pane_resizer::after { content: ''; width: 100%; height: 5px; "
            "border-radius: 3px; background: #dee2e6; } "
            "#pane_resizer:hover::after, #pane_resizer:active::after "
            "{ background: #adb5bd; } "
            "#table_card { flex: 1 1 auto; min-height: 200px; display: flex; "
            "flex-direction: column; overflow: hidden; } "
            "#table_card .card-body { flex: 1 1 auto; min-height: 0; "
            "overflow: hidden; } "
            "#table_card #table { height: 100%; } "
            # Map pane: 62% of the VISIBLE window. dvh (not vh) matters in
            # Safari, where 100vh includes the area under the URL bar and
            # would push the table below the fold; the vh line is the
            # fallback for engines without dvh support.
            "#map_card { height: clamp(240px, 62vh, calc(100vh - 240px)); } "
            "#map_card { height: clamp(240px, 62dvh, calc(100dvh - 240px)); } "
            # Bind the layout into the grid row's fixed height: bslib nests
            # main inside a .main div, so pin both, and let the wrapper fill
            # it, so the table pane only gets what the window actually has.
            # Verified 1100x640/1440x900/2200x1000: panes resize with the
            # window, no page scroll, Leaflet re-measures; no extra spacer/
            # divider element was needed (revisit if a layout regression
            # reintroduces the fixed-width feel).
            ".bslib-sidebar-layout > .main { height: 100%; min-height: 0; "
            "display: flex; flex-direction: column; overflow: hidden; } "
            ".bslib-sidebar-layout > .main > .bslib-page-main { flex: 1 1 auto; "
            "min-height: 0; display: flex; flex-direction: column; } "
            ".bslib-page-main > div { flex: 1 1 auto; min-height: 0; }"
        ),
        # Title + disclaimer as one block: inside the wrapper they sit 2px
        # apart instead of getting the sidebar's 24px flex gap between them.
        ui.div(
            ui.h3("MAA Sectional Meetings"),
            ui.p(
                "Unofficial extract of ",
                ui.tags.a(
                    "MAA webpage",
                    href=SOURCE_URL,
                    target="_blank",
                    rel="noopener noreferrer",
                ),
                *(
                    [
                        ui.tags.span(
                            _collected_line(),
                            # display:block keeps it on its own line with a
                            # much tighter leading than a <br> would give.
                            style="display: block; margin-top: 2px; line-height: 1.2;",
                        )
                    ]
                    if _collected_line()
                    else []
                ),
            ),
            style="display: flex; flex-direction: column; gap: 2px;",
        ),
        ui.tags.hr(),
        ui.input_checkbox_group(
            "buckets",
            None,  # label omitted; the hr separators + colored dots speak for it
            choices=_bucket_choices(),
            selected=["current", "upcoming", "mathfest"],
        ),
        ui.tags.hr(),
        # Searchable dropdown with region divider headers; `create` lets any
        # free text (e.g. the region word "west") be committed with Enter and
        # is matched by the filter below. Exact names still filter instantly.
        ui.input_selectize(
            "section",
            "Filter by section",
            choices=_SECTION_CHOICES,
            selected="All",
            options={"create": True},
        ),
        ui.tags.hr(),
        ui.input_radio_buttons(
            "sortby",
            "Sort by",
            choices={"date": "Date", "section": "Section"},
            selected="section",
            inline=True,
        ),
        ui.tags.hr(),
        ui.p(
            {"style": "margin-bottom: 0; line-height: 1.25;"},
            "Created by ",
            ui.tags.a(
                "Youngsu Kim",
                href=REPO_URL,
                target="_blank",
                rel="noopener noreferrer",
            ),
            ui.tags.span(
                "Source: ",
                ui.tags.a(
                    "maa.org/section-meetings",
                    href=SOURCE_URL,
                    target="_blank",
                    rel="noopener noreferrer",
                ),
                style="display: block;",
            ),
            class_="sidebar-footer",
        ),
        width="280px",
    ),
    # Map on top, table below, split by a draggable divider (like the sidebar
    # edge), together filling the viewport height. Pure DOM/JS so it behaves
    # identically under Shinylive/Pyodide; Leaflet re-measures its iframe on
    # divider drags and on any container/window size change.
    ui.div(
        ui.card(
            ui.output_ui("map"),
            id="map_card",
            style="height: clamp(240px, 62vh, calc(100vh - 240px)); min-height: 240px; flex: 0 0 auto; margin-bottom: 0;",
        ),
        ui.div(id="pane_resizer"),
        ui.card(
            ui.card_header("Meetings"),
            ui.output_ui("table"),
            id="table_card",
        ),
        style="display: flex; flex-direction: column; min-height: 0; flex: 1 1 auto;",
    ),
    ui.tags.script(
        """
        (function () {
          function invalidate(iframe) {
            try {
              var w = iframe.contentWindow;
              Object.keys(w).forEach(function (k) {
                var m = w[k];
                if (m && typeof m.invalidateSize === "function") {
                  try { m.invalidateSize(); } catch (e) {}
                }
              });
            } catch (e) {}
          }
          function bind() {
            var card = document.getElementById("map_card");
            var grip = document.getElementById("pane_resizer");
            if (!card || !grip || grip.dataset.bound) return;
            grip.dataset.bound = "1";
            var startY = 0, startH = 0, dragging = false;
            function maxCardH() {
              // never starve the table pane below 200px
              return Math.max(240, card.parentElement.clientHeight
                - grip.offsetHeight - 200);
            }
            grip.addEventListener("pointerdown", function (e) {
              dragging = true;
              startY = e.clientY;
              startH = card.getBoundingClientRect().height;
              try { grip.setPointerCapture(e.pointerId); } catch (err) {}
              e.preventDefault();
            });
            grip.addEventListener("pointermove", function (e) {
              if (!dragging) return;
              var h = Math.min(
                Math.max(startH + (e.clientY - startY), 240),
                maxCardH()
              );
              card.style.height = h + "px";
            });
            function stop() {
              if (!dragging) return;
              dragging = false;
              var f = card.querySelector("iframe");
              if (f) invalidate(f);
            }
            grip.addEventListener("pointerup", stop);
            grip.addEventListener("pointercancel", stop);
            // The cards already stretch with the window, but Leaflet keeps
            // the tile view it measured at build time; re-measure on resize
            // so the map fills the card's (re)computed width/height. Also
            // re-clamp a previously dragged height when the window shrinks.
            var rt;
            window.addEventListener("resize", function () {
              clearTimeout(rt);
              rt = setTimeout(function () {
                var h = card.getBoundingClientRect().height;
                var cap = maxCardH();
                if (card.style.height && h > cap) card.style.height = cap + "px";
                var f = card.querySelector("iframe");
                if (f) invalidate(f);
              }, 150);
            });
          }
          if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", bind);
          }
          window.addEventListener("load", bind);
          document.addEventListener("shiny:connected", bind);
          setTimeout(bind, 300);
          setTimeout(bind, 1500);
        })();
        """
    ),
)


def server(input, output, session):
    @reactive.calc
    def filtered() -> pd.DataFrame:
        view = _MEETINGS[_MEETINGS["bucket"].isin(list(input.buckets()))]
        # A chosen or typed region name filters by exact membership (so
        # "South" does not leak into SOUTHWESTERN); anything else is a
        # search: each term must match at a word start in the combined
        # "Section (Region)" haystack, case-insensitively. "All"/blank
        # matches everything.
        raw = str(input.section() or "").strip().casefold()
        if raw and raw != "all":
            exact_region = next((r for r in REGION_ORDER if r.casefold() == raw), None)
            if exact_region:
                view = view[view["region"] == exact_region]
            else:
                hay = view["_search"].astype(str).str.casefold()
                keep = pd.Series(True, index=view.index)
                for term in raw.split():
                    keep &= hay.str.contains(r"(?<!\w)" + re.escape(term), regex=True)
                view = view[keep]
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

        # MathFest dots echo the map pins' fade (same NATIONAL_RAMP), so the
        # table shows at a glance which MathFests are nearer.
        mf_sub = view[view["bucket"] == "mathfest"]
        mf_alpha = dict(
            zip(
                mf_sub.index,
                fade_alphas([str(d) for d in mf_sub["date"]], NATIONAL_RAMP),
            )
        )

        head = ui.tags.thead(
            ui.tags.tr(
                *[ui.tags.th(h, style="text-align: center;" if h == "When" else None)
                  for h in ("Section", "Date", "Location", "Speakers", "When")]
            )
        )
        body = []
        for idx, row in view.iterrows():
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
            location_note = _text(row["note"])
            location_children = []
            if location_text and row["latitude"] and row["longitude"]:
                location_children.append(
                    ui.tags.a(
                        location_text,
                        href=(
                            "https://www.google.com/maps/search/"
                            f"?api=1&query={row['latitude']},{row['longitude']}"
                        ),
                        target="_blank",
                        rel="noopener noreferrer",
                    )
                )
            elif location_text:
                location_children.append(location_text)
            if location_text and location_note:
                # dagger marks a corrected location; hover explains the fix
                location_children.append(
                    ui.tags.sup(
                        "\u2020",
                        title=location_note,
                        style="color: #6c757d; cursor: help;",
                    )
                )
            location_cell = location_children
            body.append(
                ui.tags.tr(
                    ui.tags.td(section_cell),
                    ui.tags.td(normalize_date(_text(row["date"]))),
                    ui.tags.td(*location_cell),
                    ui.tags.td(*speakers_cell),
                    ui.tags.td(
                        ui.tags.span(
                            "\u25cf",
                            style=(
                                f"color: {STATUS_COLORS.get(bucket, 'black')};"
                                + (
                                    f" opacity: {mf_alpha[idx]};"
                                    if mf_alpha.get(idx, 1.0) < 1.0
                                    else ""
                                )
                            ),
                            title=bucket,
                        ),
                        style="text-align: center;",
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
            style="height: 100%; overflow-y: auto;",
        )


app = App(app_ui, server)
