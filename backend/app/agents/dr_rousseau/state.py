"""LangGraph state definition for Dr. Rousseau."""
from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class DrRousseauState(TypedDict):
    """
    State flows through the graph at every node.

    messages: accumulated via add_messages (append-only, never overwrite)
    user_id: UUID string — passed to tools via closure, stored here for routing
    user_name: display name injected into system prompt
    user_skills: top technical skills from UserProfile
    target_roles: from UserPreferences
    preferred_locations: from UserPreferences
    has_cv: whether the user has uploaded a CV template
    thread_id: DB thread UUID for persistence after graph completion
    """

    messages: Annotated[list, add_messages]
    user_id: str
    user_name: str
    user_skills: list[str]
    target_roles: list[str]
    preferred_locations: list[str]
    has_cv: bool
    thread_id: str
