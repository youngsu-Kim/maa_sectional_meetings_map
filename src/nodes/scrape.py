import re
from pathlib import Path

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from src.config import NATIONAL_EVENTS_URL, SOURCE_URL
from src.schemas import Meeting, SectionMeetings
from src.state import PipelineState, RawSection

ACCORDION_SELECTOR = (
    "div.block.block--accordion.block--publish."
    "top-padding--default.bottom-padding--default"
)


def _make_section(row_id: str, section_name: str, content_html: str) -> RawSection:
    return RawSection(
        row_id=row_id,
        section_name=section_name,
        content_html=content_html,
    )


def _parse_legacy_accordion(soup: BeautifulSoup) -> list[RawSection]:
    """Pre-2026 MAA site: one accordion block with id-ed content divs."""
    accordion = soup.select_one(ACCORDION_SELECTOR)
    if accordion is None:
        return []

    sections: list[RawSection] = []
    for index, item in enumerate(accordion.select("div.accordion__item")):
        heading = item.select_one("h3.accordion__item-heading")
        content = item.select_one("div.accordion__content")
        if not (heading and content):
            continue
        sections.append(
            _make_section(
                content.get("id") or f"row-{index}",
                heading.get_text(strip=True),
                str(content),
            )
        )
    return sections


def _parse_wordpress_columns(soup: BeautifulSoup) -> list[RawSection]:
    """2026+ MAA site (WordPress): one wp-block-column per section."""
    sections: list[RawSection] = []
    for column in soup.select("div.wp-block-column"):
        heading = column.select_one("h4.wp-block-heading")
        if heading is None:
            continue
        name = heading.get_text(strip=True)
        heading.extract()  # content mirrors the legacy format: body without heading
        sections.append(_make_section(f"row-{len(sections)}", name, str(column)))
    return sections


def parse_sections(html: str) -> list[RawSection]:
    soup = BeautifulSoup(html, "html.parser")

    sections = _parse_legacy_accordion(soup)
    if not sections:
        sections = _parse_wordpress_columns(soup)

    if not sections:
        raise RuntimeError("No section items parsed; MAA page structure may have changed.")
    return sections


def fetch_html(url: str = SOURCE_URL) -> str:
    """Fetch the page, impersonating a browser TLS fingerprint to pass Cloudflare."""
    response = curl_requests.get(url, impersonate="chrome", timeout=30)
    response.raise_for_status()
    return response.text


# --- National meetings (structured event pages; parsed deterministically) ---

_UPCOMING_ITEM_RE = re.compile(r"^(20\d{2}):?\s*(.+?)\s*\|\s*(.+)$")


def parse_national_event_cards(events_html: str) -> list[tuple[str, str]]:
    """(name, event page URL) for national meeting cards on the events page.

    Only /event/ pages are meetings; /resource/ links (workshops, virtual
    programming) are excluded.
    """
    soup = BeautifulSoup(events_html, "html.parser")
    events: list[tuple[str, str]] = []
    seen: set[str] = set()
    for card in soup.select("a.cards__card[href]"):
        url = card["href"].strip()
        if "/event/" not in url or url in seen:
            continue
        headline = card.select_one(".card__headline")
        if headline:
            seen.add(url)
            events.append((headline.get_text(strip=True), url))
    return events


def _upcoming_meetings(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """[(date, location)] from the 'Upcoming ... Information' list.

    Items look like: '<strong>2027:</strong> New Orleans, LA | August 4-7, 2027'
    """
    for heading in soup.select("h4"):
        text = heading.get_text(strip=True).casefold()
        if text.startswith("upcoming") and "information" in text:
            ul = heading.find_next_sibling("ul")
            if ul is None:
                continue
            meetings = []
            for li in ul.find_all("li"):
                match = _UPCOMING_ITEM_RE.match(li.get_text(" ", strip=True))
                if match:
                    meetings.append((match.group(3), match.group(2)))  # (date, location)
            if meetings:
                return meetings
    return []


def parse_national_event_page(event_html: str) -> tuple[str, list[tuple[str, str]], str]:
    """(name, [(date, location)], compact content HTML) from an event page.

    Prefers the upcoming-information list (complete dates + locations);
    falls back to the event header (current event's date + location).
    The compact content HTML is kept small for a potential LLM retry.
    """
    soup = BeautifulSoup(event_html, "html.parser")
    # The first h1 on MAA pages is the site banner; the page title is scoped
    # inside the page header.
    name_el = (
        soup.select_one("h1.page-header__title")
        or soup.select_one(".page-header h1")
        or soup.select_one("main h1")
    )
    name = name_el.get_text(strip=True) if name_el else "MAA National Meeting"

    meetings = _upcoming_meetings(soup)
    if not meetings:
        date_el = soup.select_one(".event-header__date")
        location_el = soup.select_one(".event-header__location")
        if date_el and location_el:
            meetings = [
                (
                    date_el.get_text(strip=True).rstrip(", "),
                    location_el.get_text(strip=True),
                )
            ]

    # Compact retry content: header block + upcoming list.
    parts = []
    for heading in soup.select("h4"):
        if heading.get_text(strip=True).casefold().startswith("upcoming"):
            ul = heading.find_next_sibling("ul")
            if ul is not None:
                parts.append(str(heading) + str(ul))
    header = soup.select_one(".page-header__container") or name_el
    if header is not None:
        parts.insert(0, str(header))
    content_html = "\n".join(parts) or str(name_el or "")
    return name, meetings, content_html


def fetch_national_meetings() -> tuple[list[RawSection], list[SectionMeetings]]:
    """Scrape national meetings from the events page and their event pages.

    Structured data, so no LLM extraction: the returned SectionMeetings go
    straight into the graph state alongside the raw sections (which serve as
    the validation expected-name source and LLM-retry fallback).
    """
    raw_sections: list[RawSection] = []
    extracted: list[SectionMeetings] = []
    try:
        events_html = fetch_html(NATIONAL_EVENTS_URL)
        cards = parse_national_event_cards(events_html)
    except Exception:  # noqa: BLE001 - national meetings must not break sections
        return raw_sections, extracted

    for index, (card_name, url) in enumerate(cards):
        row_id = f"national-{index}"
        try:
            event_html = fetch_html(url)
            name, meetings, content_html = parse_national_event_page(event_html)
        except Exception:  # noqa: BLE001
            continue
        if not meetings:
            continue
        raw_sections.append(
            RawSection(row_id=row_id, section_name=name, content_html=content_html)
        )
        extracted.append(
            SectionMeetings(
                row_id=row_id,
                section=name or card_name,
                section_url=url,
                meetings=[
                    Meeting(date=date_text, location=location, speakers="")
                    for date_text, location in meetings
                ],
            )
        )
    return raw_sections, extracted


def scrape_node(state: PipelineState) -> dict:
    fixture = state.get("fixture_path")
    if fixture:
        html = Path(fixture).read_text(encoding="utf-8")
        sections = parse_sections(html)
        limit = state.get("limit") or 0
        if limit > 0:
            sections = sections[:limit]
        return {"raw_sections": sections}

    sections = parse_sections(fetch_html())
    national_raw, national_meetings = fetch_national_meetings()

    limit = state.get("limit") or 0
    if limit > 0:
        sections = sections[:limit]

    result: dict = {"raw_sections": sections + national_raw}
    if national_meetings:
        result["meetings"] = national_meetings
        result["retry_counts"] = {m.row_id: 1 for m in national_meetings}
    return result
