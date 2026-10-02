import os
from functools import lru_cache

from src.config import make_llm
from src.schemas import SectionMeetings
from src.state import ExtractTask, RawSection

PROMPT_TEMPLATE = """You are an agent extracting structured information from HTML for one MAA section.

Instructions:
1. Extract the section's website URL (the "Learn more information here" link) into SectionURL. Never mention that link in any other field.
2. RowID is {row_id} and Section is {section_name}; use these two values exactly as given.
3. The section may list MULTIPLE meetings (e.g. a Fall 2026 meeting and a Spring 2027 meeting). Include EVERY meeting shown: one entry per meeting in meetings, in the order they appear on the page.
4. Each meeting entry has its own Date, Location, and Speakers. Multiple speakers for one meeting go together in that meeting's speakers field.
5. A date without a year uses the year listed in the HTML.
6. If a meeting's dates are "To Be Announced" (or equivalent), keep the date text as shown but leave that meeting's location and speakers EMPTY.
7. No raw HTML may remain in any field. If something cannot be parsed, put "ERROR" in that field.
8. Missing information stays empty. Do not invent anything.

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
    llm = make_llm()
    # Groq's json_schema response format mangles nested model lists (returns
    # empty 'meetings'); its tool-calling path is mature, so use that there.
    # Ollama's constrained decoding handles json_schema natively.
    provider = (os.environ.get("LLM_MODEL") or DEFAULT_MODEL).partition(":")[0]
    method = os.environ.get("LLM_STRUCTURED_METHOD") or (
        "function_calling" if provider == "groq" else "json_schema"
    )
    structured = llm.with_structured_output(SectionMeetings, method=method)
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
        section = get_structured_llm().invoke(prompt)
    except Exception as exc:  # noqa: BLE001 - a failed call must not crash the graph
        section = SectionMeetings(
            row_id=raw["row_id"],
            section=f"EXTRACTION_ERROR: {exc!r}",
        )
    return {
        "meetings": [section],
        "retry_counts": {raw["row_id"]: task["retry_count"] + 1},
    }
