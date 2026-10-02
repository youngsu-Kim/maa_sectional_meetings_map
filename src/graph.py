from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from src.nodes.build_map import build_map_node
from src.nodes.extract import extract_one_node
from src.nodes.geocode import geocode_node
from src.nodes.scrape import scrape_node
from src.nodes.validate import rows_needing_retry, validate_node
from src.state import PipelineState


def route_after_scrape(state: PipelineState):
    """Fan out one extraction task per raw section."""
    return [
        Send("extract_one", {"raw": raw, "feedback": [], "retry_count": 0})
        for raw in state["raw_sections"]
    ]


def route_after_validate(state: PipelineState):
    """Retry invalid rows with feedback; proceed when retries are exhausted."""
    retries = rows_needing_retry(state)
    if not retries:
        return "geocode"
    raw_by_id = {raw["row_id"]: raw for raw in state["raw_sections"]}
    attempts = state.get("retry_counts", {})
    errors = state["row_errors"]
    return [
        Send(
            "extract_one",
            {
                "raw": raw_by_id[row_id],
                "feedback": errors[row_id],
                "retry_count": attempts.get(row_id, 0),
            },
        )
        for row_id in retries
    ]


def build_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("scrape", scrape_node)
    graph.add_node("extract_one", extract_one_node)
    graph.add_node("validate", validate_node)
    graph.add_node("geocode", geocode_node)
    graph.add_node("build_map", build_map_node)

    graph.add_edge(START, "scrape")
    graph.add_conditional_edges("scrape", route_after_scrape, ["extract_one"])
    graph.add_edge("extract_one", "validate")
    graph.add_conditional_edges("validate", route_after_validate, ["extract_one", "geocode"])
    graph.add_edge("geocode", "build_map")
    graph.add_edge("build_map", END)

    return graph.compile()
