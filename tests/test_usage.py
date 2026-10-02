from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.usage import TokenUsageTracker


def _result(usage_metadata=None, llm_output=None):
    message = AIMessage(content="ok", usage_metadata=usage_metadata)
    generation = ChatGeneration(message=message)
    return LLMResult(generations=[[generation]], llm_output=llm_output)


def test_tracks_usage_metadata():
    tracker = TokenUsageTracker()
    tracker.on_llm_end(_result({"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}))
    tracker.on_llm_end(_result({"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}))
    assert tracker.calls == 2
    assert tracker.input_tokens == 17
    assert tracker.output_tokens == 8
    assert tracker.total_tokens == 25
    assert "17 in" in tracker.report()


def test_tracks_llm_output_fallback():
    tracker = TokenUsageTracker()
    result = _result(
        llm_output={"token_usage": {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10}}
    )
    tracker.on_llm_end(result)
    assert tracker.calls == 1
    assert tracker.input_tokens == 4
    assert tracker.output_tokens == 6
    assert tracker.total_tokens == 10


def test_no_usage_still_counts_call():
    tracker = TokenUsageTracker()
    tracker.on_llm_end(_result())
    assert tracker.calls == 1
    assert tracker.total_tokens == 0
