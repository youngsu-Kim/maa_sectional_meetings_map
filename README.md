# MAA Sectional Meeting Map

A [LangGraph](https://langchain-ai.github.io/langgraph/) pipeline that scrapes the
[MAA section meetings page](https://maa.org/section-meetings/), extracts structured
meeting data with an LLM, geocodes the venues, and publishes an interactive
[Folium](https://python-visualization.github.io/folium/) map to GitHub Pages.
National meetings (currently [MAA MathFest](https://maa.org/event/mathfest/),
found via the [events page](https://maa.org/events/)) are included: their
structured event pages are parsed deterministically, no LLM needed.
Sections listing multiple meetings (e.g. Fall 2026 and Spring 2027) get one pin
per meeting, colored by time relative to the run date —
**grey for past meetings, orange for the current term, green for upcoming
terms** (MathFest pins are **dark purple**) — and the view auto-fits the
placed pins. The buckets are recomputed on every run, so the colors shift as
terms pass. In the Shiny apps the Show-meetings filters offer Past / Current
term / Upcoming / MathFest, the section filter is a searchable dropdown with
region divider headers where each region is also selectable ("All of West"),
and table locations link to Google Maps.

> This is an automated extract of a public web page. There could be errors;
> do not rely on this information. See the MAA page for authoritative details.

## Pipeline

```
python -m src.main [--dry-run | --fixture F | --limit N | --model M]
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ main()  (src/main.py)                                       │
│  • load .env, apply --model override                        │
│  • --dry-run → inject GoldenCsvFakeLLM + dry_run/ scratch   │
│  • graph.invoke(state, max_concurrency=LLM_MAX_CONCURRENCY, │
│                 callbacks=[TokenUsageTracker])              │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
        START ──► ┌─────────────────────────┐
                   │ scrape                  │  curl_cffi (chrome impersonation)
                   │  • dual HTML parser     │  maa.org sections → raw_sections
                   │  • national meetings    │  maa.org/events → deterministic
                   │    parsed w/o LLM       │  national-* rows (pre-extracted)
                   └───────────┬─────────────┘
                               │  route_after_scrape
                               │  (skip rows already extracted)
              ┌────────────────┼────────────────┐
              ▼ (Send)         ▼ (Send)         ▼ (Send)     ← fan-out, one task
      ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     per section, run
      │ extract_one  │  │ extract_one  │  │ extract_one  │     concurrently
      │ LLM →        │  │              │  │              │
      │ SectionMeet- │  │   (× ~30)    │  │              │   groq → function_calling
      │ ings schema  │  │              │  │              │   ollama → json_schema
      └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
             └────────────┬────┴────────────────┘
                          ▼ (all appends merge via operator.add)
                 ┌──────────────────┐
                 │ validate         │  merge by row_id (last write wins),
                 │                  │  check: section name match, no HTML/URLs,
                 │                  │  non-empty meetings, length/repetition,
                 │                  │  TBA consistency → row_errors, failed_rows
                 └────────┬─────────┘
                          │  route_after_validate
              errors &    ├──────────────────────────────┐
              retry_count │                              │ no errors (or
              ≤ 2         ▼                              │ retries exhausted)
              ┌───────────────────────┐                  │
              │ Send back to          │   up to initial  │
              │ extract_one with the  │   + 2 retries    │
              │ errors as feedback    │   per section    │
              └───────────────────────┘                  │
                                                         ▼
                                              ┌─────────────────────┐
                                              │ geocode             │
                                              │  1. location_       │
                                              │     corrections.csv │
                                              │  2. geocode_cache   │
                                              │     .csv (hits)     │
                                              │  3. geopy Nominatim │
                                              │     region-aware    │
                                              │     (section_       │
                                              │      regions.csv:   │
                                              │      country codes, │
                                              │      viewbox)       │
                                              └──────────┬──────────┘
                                                         ▼
                                              ┌─────────────────────┐
                                              │ build_map           │
                                              │  • data/meetings_   │
                                              │    latest.csv       │
                                              │  • site/index.html  │
                                              │    (folium, colors, │
                                              │    fade, legend)    │
                                              └──────────┬──────────┘
                                                         ▼
                        END ──► back in main()
                          │
                          ├─ write data/last_run.txt            (skipped if dry-run)
                          ├─ snapshot data/archive/meetings_YYYY-MM-DD.csv
                          ├─ print summary (sections, calls, failures, cache, tokens)
                          └─ exit code: 1 if failed_rows else 0   ← CI gate
```

The `Send` API fans the work out dynamically (one `extract_one` task per
section, plus one per retried row), and the `operator.add` reducer merges the
parallel results into shared state; the retry loop is just a conditional edge
pointing from `validate` back to `extract_one`.

## Setup

```bash
uv venv --python 3.12 .venv   # or: python3 -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"    # or: pip install -e ".[dev]"
cp .env.example .env          # then fill in your API key
```

### Models

The model is configured with `LLM_MODEL` (see `.env.example`):

| Mode | Setting | Notes |
|---|---|---|
| Hosted (CI default) | `LLM_MODEL=groq:qwen/qwen3.8-27b` | free tier, needs `GROQ_API_KEY` from [console.groq.com](https://console.groq.com/keys) |
| Local | `LLM_MODEL=ollama:qwen3.8:27b` | requires `ollama serve` |

Keep `LLM_MAX_CONCURRENCY` low for the Groq free tier (8K tokens/min).

## Usage

```bash
python -m src.main                # full run (scrape live page)
python -m src.main --limit 3      # smoke test: first 3 sections only
python -m src.main --dry-run      # fully offline: fixture HTML + fake LLM
python -m src.main --fixture tests/fixtures/section_meetings.html  # scrape from file, rest live
```

Outputs: `site/index.html` (the map) and `data/meetings_latest.csv` — the
canonical current data that the apps and the Shinylive export read. Every
real run also archives a dated copy under `data/archive/meetings_YYYY-MM-DD.csv`
(same-day re-runs overwrite that day's snapshot), so the history of what the
MAA page said is browsable and diffable; `git log` on the archive shows when
things changed. `--dry-run` writes to a `dry_run/` scratch directory and never
touches the real data.
Geocoding is region-aware: `data/section_regions.csv` maps each MAA section
to the country codes (and optionally a bounding box) of its territory, so
ambiguous venue names resolve inside the section's region — e.g. "St. Thomas
Aquinas College" exists in Australia and California, but Metro New York's
campus is in Sparkill, NY. Sections spanning the US-Canada border (Seaway,
Pacific Northwest) search `us,ca`. Unlisted sections default to `us`.
`data/geocode_cache.csv` caches venue coordinates so repeated runs stay
within the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/).
`data/location_corrections.csv` lists known typos on the MAA page (e.g.
"Omaha, NB" for Nebraska): corrected locations are what gets listed and
pinned, with a dagger (&dagger;) marker whose tooltip shows the original
text and the reason, so readers can verify the fix themselves.

## Tests

```bash
pytest                       # offline unit tests (no network, no LLM)
LLM_MODEL=... pytest tests/test_golden_llm.py   # live-LLM comparison vs golden CSV
```

## Interactive Shiny front ends

Two variants read `data/meetings_latest.csv` and recompute the past/current/
upcoming buckets at startup, so colors stay current between pipeline runs.
The map and table panes are separated by a draggable divider (like the
sidebar's edge) so either can be enlarged, and a basemap switcher
(bottom-right of the map) toggles Esri satellite imagery for street-level
detail when zoomed in.

**Server version** (Python [Shiny](https://shiny.posit.co/py/)):

```bash
uv pip install -e ".[shiny]"   # or: pip install -e ".[shiny]"
shiny run app.py --reload      # http://localhost:8000
```

**Browser-only version** ([Shinylive](https://shiny.posit.co/py/shinylive/)):
the same app compiled to WebAssembly via Pyodide — no server, deployable
statically. First load downloads the Python runtime (~40 MB, cached by a
service worker afterwards), then the app runs entirely in the visitor's
browser:

```bash
uv pip install -e ".[shinylive]"
python -c "from shinylive._export import export; export('shinylive_app', 'site/shinylive')"
python3 -m http.server --directory site  # open /shinylive/
```

The GitHub Actions workflow builds this export on every run, so GitHub Pages
serves the static Folium map at `/` and the Shinylive app at `/shinylive/`.
`shinylive_app/meeting_time.py` is a synced copy of the repo-root
`meeting_time.py` (a test enforces the sync); `app.py` and
`shinylive_app/app.py` are kept in step manually.
The region divider headers come from `data/section_groups.csv` (a
test checks it against the data, so a new or renamed MAA section fails CI
until the CSV catches up); unlisted sections fall back to an "Other" group.

Other platforms worth a look for this kind of dashboard:
[Streamlit](https://streamlit.io/) (fastest prototypes; free hosting on
Streamlit Community Cloud or HF Spaces), [Dash](https://dash.plotly.com/)
(callback-based, enterprise-flavored), [Panel](https://panel.holoviz.org/)
(notebook-first), R [Shiny](https://shiny.posit.co/) (the original; the
`leaflet` R package is excellent), and static options like
[Quarto](https://quarto.org/) or [Observable](https://observablehq.com/) that
deploy free on GitHub Pages like the current map.

## GitHub Actions

`.github/workflows/update_map.yml` runs the pipeline weekly (Mon 11:00 UTC) or on
demand, commits the refreshed data, and deploys `site/` to GitHub Pages.
Required secret: `GROQ_API_KEY`.

## License

[MIT](LICENSE)

Built upon the CC0-licensed static-map experiment originally committed to this
repository in October 2025.

---

Assisted by GLM-5.3-NVFP4, hosted on the National Research Platform.
