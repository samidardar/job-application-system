"""Pydantic schemas for the /chat endpoint."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10_000)
    thread_id: UUID | None = Field(
        default=None,
        description="Existing thread UUID. Omit to start a new conversation.",
    )


class ChatMessageOut(BaseModel):
    role: str  # "human" | "ai" | "tool"
    content: str
    timestamp: str
    tool_name: str | None = None


class ChatThreadOut(BaseModel):
    id: UUID
    title: str | None
    messages: list[ChatMessageOut]
    created_at: datetime
    updated_at: datetime


class ChatThreadListItem(BaseModel):
    id: UUID
    title: str | None
    message_count: int
    updated_at: datetime
