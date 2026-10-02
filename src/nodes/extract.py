import os
from functools import lru_cache

from src.config import make_llm
from src.schemas import SectionMeeting
from src.state import ExtractTask, RawSection

PROMPT_TEMPLATE = """You are an agent extracting structured information from HTML for one MAA section.

Instructions:
1. Extract Date, Location, Speakers, and SectionURL from the HTML below.
2. RowID is {row_id} and Section is {section_name}; use these two values exactly as given.
3. If the page lists multiple meetings for this section, use the FIRST one only. Ignore later meetings entirely.
4. A date without a year uses the year listed in the HTML.
5. Multiple speakers for the chosen meeting go together in the speakers field.
6. The section's website link ("Learn more information here") goes ONLY into section_url. Never mention that link in any other field.
7. If meeting dates are "To Be Announced" (or equivalent), keep the date text as shown but leave location and speakers EMPTY.
8. No raw HTML may remain in any field. If something cannot be parsed, put "ERROR" in that field.
9. Missing information stays empty. Do not invent anything.

{feedback}HTML:
{html}"""


def build_prompt(raw: RawSection, feedback: list[str] | None = None) -> str:
    if feedback:
        fb = (
            "Your previous attempt was rejected for these problems; fix them:\n"
            + "\n".join(f"- {item}" for item in feedback)
            + "\n\n"
        )
    else:
        fb = ""
    return PROMPT_TEMPLATE.format(
        row_id=raw["row_id"],
        section_name=raw["section_name"],
        feedback=fb,
        html=raw["content_html"],
    )


@lru_cache(maxsize=1)
def _default_structured_llm():
    method = os.environ.get("LLM_STRUCTURED_METHOD", "json_schema")
    llm = make_llm()
    structured = llm.with_structured_output(SectionMeeting, method=method)
    return structured.with_retry(stop_after_attempt=4, wait_exponential_jitter=True)


_llm_factory = None


def set_llm_factory(factory) -> None:
    """Inject a custom LLM factory (used by --dry-run and tests)."""
    global _llm_factory
    _llm_factory = factory
    _default_structured_llm.cache_clear()


def get_structured_llm():
    if _llm_factory is not None:
        return _llm_factory()
    return _default_structured_llm()


def extract_one_node(task: ExtractTask) -> dict:
    raw = task["raw"]
    prompt = build_prompt(raw, task["feedback"])
    try:
        meeting = get_structured_llm().invoke(prompt)
    except Exception as exc:  # noqa: BLE001 - a failed call must not crash the graph
        meeting = SectionMeeting(
            row_id=raw["row_id"],
            section=f"EXTRACTION_ERROR: {exc!r}",
        )
    return {
        "meetings": [meeting],
        "retry_counts": {raw["row_id"]: task["retry_count"] + 1},
    }
