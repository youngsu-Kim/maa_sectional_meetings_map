import threading

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class TokenUsageTracker(BaseCallbackHandler):
    """Accumulates token usage across every LLM call in a pipeline run.

    Attached via config callbacks, so it counts calls made through
    with_structured_output and with_retry, including failed attempts.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        usage = self._extract_usage(response)
        with self._lock:
            self.calls += 1
            if usage:
                self.input_tokens += usage.get("input_tokens", 0)
                self.output_tokens += usage.get("output_tokens", 0)
                self.total_tokens += usage.get("total_tokens") or (
                    usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                )

    @staticmethod
    def _extract_usage(response: LLMResult) -> dict:
        # Standardized path: AIMessage.usage_metadata (populated by ChatOllama and ChatGroq).
        try:
            for generations in response.generations:
                for generation in generations:
                    usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
                    if usage:
                        return dict(usage)
        except (AttributeError, IndexError, TypeError):
            pass

        # Fallback: LLMResult.llm_output["token_usage"] with OpenAI/Ollama-style keys.
        llm_output = getattr(response, "llm_output", None) or {}
        raw = llm_output.get("token_usage") or llm_output
        if raw:
            return {
                "input_tokens": raw.get("prompt_tokens", raw.get("prompt_eval_count", 0)),
                "output_tokens": raw.get("completion_tokens", raw.get("eval_count", 0)),
                "total_tokens": raw.get("total_tokens", 0),
            }
        return {}

    def report(self) -> str:
        return (
            f"{self.calls} calls, "
            f"{self.input_tokens} in / {self.output_tokens} out / "
            f"{self.total_tokens} total tokens"
        )
