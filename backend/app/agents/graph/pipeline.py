"""
Postulio LangGraph Pipeline.

Graph flow:
  START → scrape → detect_ghosts → match → research →
          generate_docs → qa_gate → submit → finalize → END

Each node is an async function that receives and returns PipelineState slices.
"""
import logging

from langgraph.graph import StateGraph, START, END

from app.agents.graph.state import PipelineState
from app.agents.graph.nodes.scraping import node_scrape
from app.agents.graph.nodes.ghost_detector import node_detect_ghosts
from app.agents.graph.nodes.matching import node_match
from app.agents.graph.nodes.research import node_research
from app.agents.graph.nodes.generate_docs import node_generate_docs
from app.agents.graph.nodes.qa_gate import node_qa_gate
from app.agents.graph.nodes.application import node_submit
from app.agents.graph.nodes.finalize import node_finalize

logger = logging.getLogger(__name__)


def build_pipeline():
    """Build and compile the Postulio LangGraph pipeline."""
    graph = StateGraph(PipelineState)

    # Register nodes
    graph.add_node("scrape", node_scrape)
    graph.add_node("detect_ghosts", node_detect_ghosts)
    graph.add_node("match", node_match)
    graph.add_node("research", node_research)
    graph.add_node("generate_docs", node_generate_docs)
    graph.add_node("qa_gate", node_qa_gate)
    graph.add_node("submit", node_submit)
    graph.add_node("finalize", node_finalize)

    # Linear edges
    graph.add_edge(START, "scrape")
    graph.add_edge("scrape", "detect_ghosts")
    graph.add_edge("detect_ghosts", "match")
    graph.add_edge("match", "research")
    graph.add_edge("research", "generate_docs")
    graph.add_edge("generate_docs", "qa_gate")
    graph.add_edge("qa_gate", "submit")
    graph.add_edge("submit", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


# Singleton — compiled once at import time
pipeline = build_pipeline()
