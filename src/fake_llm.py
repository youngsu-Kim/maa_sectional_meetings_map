"""Offline stand-in for the structured LLM, used by --dry-run."""

import csv
import re

from src.schemas import SectionMeeting

_ROW_ID_RE = re.compile(r"RowID is (row-[\w-]+)")


def normalize_row_id(row_id: str) -> str:
    return row_id.strip().removeprefix("row-")


class GoldenCsvFakeLLM:
    """Answers extraction prompts from a golden CSV instead of calling a model."""

    def __init__(self, csv_path):
        self.rows: dict[str, dict] = {}
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = normalize_row_id(row.get("row") or row.get("row_id") or "")
                if key:
                    self.rows[key] = row

    def invoke(self, prompt: str, config=None, **kwargs) -> SectionMeeting:
        match = _ROW_ID_RE.search(prompt)
        key = normalize_row_id(match.group(1)) if match else ""
        row = self.rows.get(key, {})
        return SectionMeeting(
            row_id=f"row-{key}" if key else "",
            section=row.get("Section", ""),
            date=row.get("Date", ""),
            location=row.get("Location", ""),
            speakers=row.get("Speakers", ""),
            section_url=row.get("SectionURL", ""),
        )