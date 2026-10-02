import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"
FIXTURES_DIR = ROOT / "tests" / "fixtures"

SOURCE_URL = "https://maa.org/section-meetings/"
GEOCODE_CACHE_PATH = DATA_DIR / "geocode_cache.csv"
LOCATION_CORRECTIONS_PATH = DATA_DIR / "location_corrections.csv"
MEETINGS_CSV_PATH = DATA_DIR / "meetings_latest.csv"
MAP_PATH = SITE_DIR / "index.html"

# Nominatim usage policy requires a descriptive User-Agent with contact info.
# Replace the URL with your actual repository once published.
USER_AGENT = "maa-sectional-meeting-map/1.0 (https://github.com/maa-sectional-meeting-map)"

DEFAULT_MODEL = "groq:qwen/qwen3.8-27b"
MAX_EXTRACTION_RETRIES = 2


def make_llm(spec: str | None = None):
    """Build a chat model from a 'provider:model' spec.

    Supported providers: 'groq:<model-id>' and 'ollama:<local-tag>'.
    """
    spec = (spec or os.environ.get("LLM_MODEL") or DEFAULT_MODEL).strip()
    provider, sep, model = spec.partition(":")
    if not sep or not model:
        raise ValueError(f"LLM_MODEL must look like 'provider:model', got {spec!r}")

    if provider == "groq":
        from langchain_groq import ChatGroq

        kwargs: dict = {
            "model": model,
            "temperature": 0,
            "max_retries": 5,
            # Bound the response size: a meeting record needs ~200 tokens.
            "max_tokens": int(os.environ.get("GROQ_MAX_TOKENS", "1024")),
        }
        try:
            return ChatGroq(**kwargs, reasoning_format="hidden")
        except (TypeError, ValueError):
            # Older langchain-groq without reasoning-format support.
            return ChatGroq(**kwargs)

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        # Cap the context window: qwen3.8's 262K default allocates a huge KV
        # cache per parallel request and grinds local inference to a halt.
        kwargs = {
            "model": model,
            "temperature": 0,
            "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            "num_ctx": int(os.environ.get("OLLAMA_NUM_CTX", "8192")),
            # Bound the response size: prevents degenerate repetition loops
            # from generating thousands of tokens.
            "num_predict": int(os.environ.get("OLLAMA_NUM_PREDICT", "512")),
        }
        try:
            # Qwen3-family models emit thinking tokens unless disabled.
            return ChatOllama(**kwargs, reasoning=False)
        except (TypeError, ValueError):
            # Older langchain-ollama without reasoning support.
            return ChatOllama(**kwargs)

    raise ValueError(f"Unsupported LLM provider {provider!r} (use 'groq:...' or 'ollama:...')")
