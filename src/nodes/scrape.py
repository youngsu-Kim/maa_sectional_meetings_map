from pathlib import Path

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from src.config import SOURCE_URL
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


def scrape_node(state: PipelineState) -> dict:
    fixture = state.get("fixture_path")
    if fixture:
        html = Path(fixture).read_text(encoding="utf-8")
    else:
        html = fetch_html()
    sections = parse_sections(html)

    limit = state.get("limit") or 0
    if limit > 0:
        sections = sections[:limit]

    return {"raw_sections": sections}
