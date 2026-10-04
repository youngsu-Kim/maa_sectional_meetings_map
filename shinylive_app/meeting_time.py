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
_MONTH_ABBR = {
    "jan": "Jan", "feb": "Feb", "mar": "Mar", "apr": "Apr", "may": "May",
    "jun": "Jun", "jul": "Jul", "aug": "Aug", "sep": "Sep", "oct": "Oct",
    "nov": "Nov", "dec": "Dec",
}
_MONTH_ABBR_PERIOD_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.")


def normalize_date(date: str) -> str:
    """Normalize month names to three-letter abbreviations.

    'March 27-28, 2026' -> 'Mar 27-28, 2026'; 'Feb. 20-21, 2026' -> 'Feb 20-21, 2026'.
    Strings without a month name are returned unchanged.
    """
    abbreviated = _MONTHS_RE.sub(
        lambda m: _MONTH_ABBR[m.group(0)[:3].casefold()], date
    )
    # Drop periods directly after the abbreviation ("Feb. 20" -> "Feb 20").
    return _MONTH_ABBR_PERIOD_RE.sub(r"\1", abbreviated)


def term_of(date: str) -> str:
    """Classify a meeting date as 'fall' or 'spring' (empty if undeterminable).

    July/August count as fall, matching the academic-term ordering used by
    meeting_status (Fall = Jul-Dec, Spring = Jan-Jun).
    """
    months = {m[:3].casefold() for m in _MONTHS_RE.findall(date)}
    if months & {"jul", "aug", "sep", "oct", "nov", "dec"}:
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


# Pin opacity by temporal rank within a bucket: soonest fully solid, then a
# hand-tuned fade. Ranks past the end of the ramp keep the last value.
# UPCOMING fades gently and never reaches PAST_ALPHA, so far-future pins do
# not look "past"; NATIONAL (MathFest) has exactly a handful of dates and
# uses the steeper requested ramp.
UPCOMING_RAMP = (1.0, 0.85, 0.75, 0.65)
NATIONAL_RAMP = (1.0, 0.70, 0.55, 0.45)
# Past meetings get a constant dimmed opacity, strictly below both ramps so
# they never blend into the faintest future pins.
PAST_ALPHA = 0.40


def fade_alphas(
    dates: list[str], ramp: tuple[float, ...] = UPCOMING_RAMP
) -> list[float]:
    """Pin opacity per date: soonest = ramp[0], later ranks fade along the ramp.

    Ties (same year/month) share the same alpha so equal dates do not look
    arbitrarily different. Input order is preserved in the output.
    """
    if not dates:
        return []
    order = sorted(range(len(dates)), key=lambda i: meeting_sort_key(dates[i]))
    alphas = [1.0] * len(dates)
    prev_key = None
    distinct = -1
    for idx in order:
        key = meeting_sort_key(dates[idx])
        if key != prev_key:
            distinct += 1
            prev_key = key
        alphas[idx] = ramp[min(distinct, len(ramp) - 1)]
    return alphas


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
