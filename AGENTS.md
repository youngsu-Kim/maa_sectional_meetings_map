# AGENTS.md

## Project location

Canonical checkout: `/Users/006501270/git_local_files/maa_sectional_meetings_map`
GitHub: https://github.com/youngsu-Kim/maa_sectional_meetings_map (deploys to GitHub Pages)

## What this is

LangGraph pipeline that scrapes maa.org section-meeting pages (plus the national
MathFest), extracts structured meeting data with an LLM (Groq in CI, Ollama
locally; Groq needs `method="function_calling"`), geocodes venues, and publishes:

- `/` — static folium map (built by `src/nodes/build_map.py`)
- `/shinylive/` — browser-only Shiny (Pyodide) app, twin of `app.py`
- `app.py` — local/server Shiny app
- `/shinylive-r/` — R Shiny (webR) twin, `shinylive_r_app/`

## Key commands

```bash
uv pip install -e ".[dev,shiny,shinylive]"    # Python 3.12, .venv
.venv/bin/python -m pytest -q                 # tests incl. sync + curation gates
.venv/bin/shiny run app.py                    # local Shiny (use nohup ... & to keep alive)
python -c "from shinylive._export import export; export('shinylive_app', 'site/shinylive')"
gh workflow run update_map.yml                # DEPLOY — pushing does NOT deploy
```

Deploy only happens via the `update-map` workflow (Mondays 11:00 UTC or manual
dispatch); it scrapes fresh data, runs tests, rebuilds both shinylive exports,
commits refreshed `data/`, and publishes `site/` to Pages.

## R toolchain

- R 4.6.1 via Homebrew: `/opt/homebrew/opt/r/bin/R` (`brew link r` puts
  `R`/`Rscript` on PATH); packages install into `/opt/homebrew/lib/R/4.6/site-library`
- `/usr/local/bin/R` is a broken symlink from an old CRAN install — ignore it
- R packages cannot be managed by uv (Python-only); use `install.packages()`
- **Makeconf caveat**: a `brew reinstall/upgrade r` regenerates
  `lib/R/etc/Makeconf` with FLIBS pointing at a gcc path that may not match
  the installed gcc bottle (symptom: every compiled package fails with
  `library 'emutls_w' not found`). Fix: sed the `aarch64-apple-darwinNN/16`
  path in FLIBS to the dir that actually exists under
  `/opt/homebrew/opt/gcc/lib/gcc/current/gcc/`
- Local spatial stack (CRAN leaflet hard-imports raster+sf): system libs
  `gdal geos proj udunits` via brew; install terra/sf with
  `--with-proj-lib=/opt/homebrew/opt/proj/lib
  --with-sqlite3-lib=/opt/homebrew/opt/sqlite/lib` configure args
- R commands:
  - `Rscript shinylive_r_app/selftest.R` — logic parity tests (base R only)
  - `Rscript -e 'shiny::runApp("shinylive_r_app", port = 8130)'` — native run
    (launch detached via python3 `subprocess.Popen(start_new_session=True)`;
    plain `nohup ... &` is unreliable in the tool shell)
  - `Rscript -e 'shinylive::export("shinylive_r_app", "site/shinylive-r")'`
    (first run downloads web assets to `~/Library/Caches/shinylive`)

## Conventions / gotchas

- `app.py` and `shinylive_app/app.py` are twins kept in step manually (differ
  only in docstrings)
- `meeting_time.py` ↔ `shinylive_app/meeting_time.py` must be byte-identical
  (test-enforced); `shinylive_r_app/meeting_time.R` is the R logic twin —
  keep it in step manually, `Rscript shinylive_r_app/selftest.R` guards it
- R Shiny choice lists are mirrored from Python: `c(<label> = <value>)`
  where Python uses `{<value>: <label>}`
- CI copies data CSVs into the app `data/` dirs before export; `site/` is
  gitignored (built fresh in CI, never committed)
- Git identity: `youngsu-Kim <21338460+youngsu-Kim@users.noreply.github.com>`
- Background servers: use `nohup ... &` (plain `&` dies with the shell session)
- Preview ports: 8123 (shiny), 8128 (`python3 -m http.server 8128 --directory site`)
- MAA site needs curl_cffi impersonation (Cloudflare); MAA has no official
  super-region taxonomy — `data/section_groups.csv` is our own construct
