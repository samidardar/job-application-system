"""
LangGraph state machine for Dr. Rousseau.

Graph topology:
  chatbot ──(has tool calls?)──► tools ──► chatbot
         └──(no tool calls)──► END

The chatbot node always prepends a fresh SystemMessage so that
user context (skills, CV status, etc.) is always up to date.
"""
from __future__ import annotations

import logging
import uuid

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.dr_rousseau.prompts import build_system_prompt
from app.agents.dr_rousseau.state import DrRousseauState
from app.agents.dr_rousseau.tools import make_tools
from app.config import settings

logger = logging.getLogger(__name__)


def make_graph(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> CompiledStateGraph:
    """
    Compile a fresh LangGraph graph for a single chat request.
    Called once per SSE request; the `db` session and `user_id` are
    bound into tools via closure.
    """
    tools = make_tools(db, user_id)
    tool_node = ToolNode(tools)

    llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        api_key=settings.anthropic_api_key,
        streaming=True,
        temperature=0.3,
        max_tokens=4096,
    ).bind_tools(tools)

    # ── Nodes ─────────────────────────────────────────────────────────────

    async def chatbot(state: DrRousseauState) -> dict:
        """Main LLM node — injects fresh system prompt and calls Claude."""
        system_prompt = build_system_prompt(
            user_name=state["user_name"],
            skills=state.get("user_skills"),
            target_roles=state.get("target_roles"),
            preferred_locations=state.get("preferred_locations"),
            has_cv=state.get("has_cv", False),
        )
        messages_with_system = [SystemMessage(content=system_prompt)] + list(state["messages"])
        response = await llm.ainvoke(messages_with_system)
        return {"messages": [response]}

    # ── Routing ───────────────────────────────────────────────────────────

    def route_after_chatbot(state: DrRousseauState) -> str:
        """If the last AI message has tool calls, route to tools. Otherwise END."""
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    # ── Graph assembly ────────────────────────────────────────────────────

    builder = StateGraph(DrRousseauState)
    builder.add_node("chatbot", chatbot)
    builder.add_node("tools", tool_node)

    builder.set_entry_point("chatbot")
    builder.add_conditional_edges(
        "chatbot",
        route_after_chatbot,
        {"tools": "tools", END: END},
    )
    builder.add_edge("tools", "chatbot")

    return builder.compile()
