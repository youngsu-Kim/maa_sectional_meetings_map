"""Time-relative classification of MAA meeting dates.

Pure stdlib on purpose: this module is shared by the LangGraph pipeline,
the server Shiny app (app.py), and the browser-only Shinylive export
(shinylive_app/meeting_time.py is a synced copy of this file).
"""

import re
from datetime import date

# Full or abbreviated month names ("Feb.", "Oct", "September", ...).
_MONTHS_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"(20\d{2})")
_MONTH_NUMBERS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def term_of(date: str) -> str:
    """Classify a meeting date as 'fall' or 'spring' (empty if undeterminable)."""
    months = {m[:3].casefold() for m in _MONTHS_RE.findall(date)}
    if months & {"sep", "oct", "nov", "dec"}:
        return "fall"
    if months & {"jan", "feb", "mar", "apr", "may", "jun"}:
        return "spring"
    text = date.casefold()
    if "fall" in text:
        return "fall"
    if "spring" in text:
        return "spring"
    return ""


def term_label(date: str) -> str:
    """Human label like 'Fall 2026'; falls back to the raw date text."""
    term = term_of(date)
    if not term:
        return date
    year = _YEAR_RE.search(date)
    return f"{term.capitalize()} {year.group(1)}" if year else term.capitalize()


def _parse_month_year(date_str: str):
    months = _MONTHS_RE.findall(date_str)
    year = _YEAR_RE.search(date_str)
    if not months or not year:
        return None
    return int(year.group(1)), _MONTH_NUMBERS[months[0][:3].casefold()]


def _term_key(year: int, month: int) -> tuple[int, int]:
    """Academic-year ordering: Fall 2026 < Spring 2027 < Fall 2027 < ..."""
    if month <= 6:
        return (year - 1, 1)  # spring belongs to the academic year that started prior fall
    return (year, 0)  # fall (July-Aug meetings count toward the upcoming fall term)


def current_term_label(today: date | None = None) -> str:
    today = today or date.today()
    if today.month <= 6:
        return f"Spring {today.year}"
    return f"Fall {today.year}"


def meeting_sort_key(date_str: str) -> tuple[int, int]:
    """Chronological sort key (year, month); unparseable dates sort last."""
    parsed = _parse_month_year(date_str)
    if parsed is None:
        return (9999, 12)
    return parsed


def meeting_status(date_str: str, today: date | None = None) -> str:
    """Bucket a meeting as 'past', 'current', or 'upcoming' relative to today.

    Term-granular: a meeting stays 'current' for the whole academic term it
    belongs to (Fall = Jul-Dec, Spring = Jan-Jun) once that term arrives, so
    the buckets shift automatically as time passes.
    """
    today = today or date.today()
    parsed = _parse_month_year(date_str)
    if parsed is None:
        return "current"  # unparseable dates stay visible under the current bucket
    year, month = parsed

    if (year, month) < (today.year, today.month):
        return "past"

    meeting_key = _term_key(year, month)
    today_key = _term_key(today.year, today.month)
    if meeting_key < today_key:
        return "past"
    if meeting_key == today_key:
        return "current"
    return "upcoming"
