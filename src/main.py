import argparse
import os
import shutil
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.config import ARCHIVE_DIR, FIXTURES_DIR, LAST_RUN_PATH, MEETINGS_CSV_PATH, ROOT


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="Scrape MAA section meetings, extract with an LLM, geocode, build the map.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="offline mode: fixture HTML + golden-CSV fake LLM + no network calls",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="only process the first N sections (0 = all); handy for smoke tests",
    )
    parser.add_argument(
        "--model",
        help="override LLM_MODEL, e.g. ollama:qwen3.8:27b or groq:qwen/qwen3.8-27b",
    )
    parser.add_argument(
        "--fixture",
        help="path to a saved section-meetings HTML file (implies offline scrape)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    load_dotenv()
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    fixture_path = args.fixture
    init_state: dict = {"limit": args.limit or 0}

    if args.dry_run:
        from src.fake_llm import GoldenCsvFakeLLM
        from src.nodes import extract

        fixture = fixture_path or str(FIXTURES_DIR / "section_meetings.html")
        extract.set_llm_factory(
            lambda: GoldenCsvFakeLLM(FIXTURES_DIR / "golden_meetings.csv")
        )
        # Scratch outputs: a dry run must never clobber the real
        # meetings_latest.csv / site map with golden fixture data.
        scratch = ROOT / "dry_run"
        scratch.mkdir(exist_ok=True)
        init_state.update(
            dry_run=True,
            fixture_path=fixture,
            map_path_out=str(scratch / "index.html"),
            csv_path_out=str(scratch / "meetings.csv"),
        )
    elif fixture_path:
        # --fixture without --dry-run: scrape from file, everything else live
        init_state.update(fixture_path=fixture_path)

    from src.graph import build_graph
    from src.usage import TokenUsageTracker

    graph = build_graph()
    tracker = TokenUsageTracker()
    config = {
        "max_concurrency": int(os.environ.get("LLM_MAX_CONCURRENCY", "2")),
        "callbacks": [tracker],
    }
    final_state = graph.invoke(init_state, config=config)

    # Record the collection date so the front ends can display it
    # ("Data collected: ..."). Dry runs replay fixtures and must not
    # overwrite the real timestamp or the archive.
    if not args.dry_run:
        LAST_RUN_PATH.write_text(date.today().isoformat(), encoding="utf-8")
        snapshot = save_dated_snapshot(MEETINGS_CSV_PATH, ARCHIVE_DIR, date.today())
        print(f"archive:           {snapshot}")

    _print_summary(final_state, tracker)
    return 0


def save_dated_snapshot(csv_path, archive_dir, today: date) -> Path:
    """Archive the scraped data as data/archive/meetings_YYYY-MM-DD.csv.

    meetings_latest.csv stays the canonical current file (the apps and the
    Shinylive export read it); the dated snapshots keep the run history so
    changes are browsable and diffable. Re-runs on the same day overwrite
    that day's snapshot.
    """
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    destination = archive_dir / f"meetings_{today.isoformat()}.csv"
    shutil.copy2(csv_path, destination)
    return destination


def _print_summary(state: dict, tracker=None) -> None:
    attempts = state.get("retry_counts", {})
    total_attempts = sum(attempts.values())
    print(f"sections:          {len(state.get('raw_sections', []))}")
    print(f"extraction calls:  {total_attempts}")
    print(f"valid rows:        {len(state.get('merged', {})) - len(state.get('row_errors', {}))}")
    print(f"meetings listed:   {len(state.get('geocoded', []))}")
    failed = state.get("failed_rows", [])
    print(f"failed rows:       {len(failed)}")
    for row_id in failed:
        print(f"  - {row_id}: {state['row_errors'].get(row_id)}")
    print(f"cache hits/misses: {state.get('cache_hits', 0)}/{state.get('cache_misses', 0)}"
          f" (unresolved: {state.get('cache_failures', 0)})")
    corrections = state.get("corrections_applied", [])
    print(f"corrections:       {len(corrections)}")
    for item in corrections:
        print(f"  - {item}")
    if tracker is not None:
        print(f"llm usage:         {tracker.report()}")
    print(f"map:               {state.get('map_path')}")
    print(f"csv:               {state.get('csv_path')}")


if __name__ == "__main__":
    raise SystemExit(main())
