# MAA Sectional Meeting Map

A [LangGraph](https://langchain-ai.github.io/langgraph/) pipeline that scrapes the
[MAA section meetings page](https://maa.org/section-meetings/), extracts structured
meeting data with an LLM, geocodes the venues, and publishes an interactive
[Folium](https://python-visualization.github.io/folium/) map to GitHub Pages.

```
scrape -> extract (fan-out) -> validate -> [retry] -> geocode -> build_map
```

> This is an automated extract of a public web page. There could be errors;
> do not rely on this information. See the MAA page for authoritative details.

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

Outputs: `site/index.html` (the map) and `data/meetings_latest.csv`.
`data/geocode_cache.csv` caches venue coordinates so repeated runs stay within
the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/).

## Tests

```bash
pytest                       # offline unit tests (no network, no LLM)
LLM_MODEL=... pytest tests/test_golden_llm.py   # live-LLM comparison vs golden CSV
```

## GitHub Actions

`.github/workflows/update_map.yml` runs the pipeline weekly (Mon 11:00 UTC) or on
demand, commits the refreshed data, and deploys `site/` to GitHub Pages.
Required secret: `GROQ_API_KEY`.

## License

[MIT](LICENSE)

---

Assisted by GLM-5.3-NVFP4, hosted on the National Research Platform.
