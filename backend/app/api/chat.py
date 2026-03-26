"""
/api/v1/chat — Dr. Rousseau SSE streaming endpoint.

Event stream format (text/event-stream):
  event: status     data: {"message": "🔍 Analyse de l'offre en cours..."}
  event: token      data: {"text": "Bonjour..."}
  event: tool_end   data: {"tool": "analyze_job_url", "summary": "..."}
  event: done       data: {"thread_id": "<uuid>"}
  event: error      data: {"message": "..."}
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.dr_rousseau.graph import make_graph
from app.agents.dr_rousseau.tools import TOOL_STATUS
from app.api.deps import get_current_user
from app.database import get_db
from app.models.chat import ChatThread
from app.models.user import User, UserPreferences, UserProfile
from app.schemas.chat_schemas import ChatRequest, ChatThreadListItem, ChatThreadOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# Maximum messages to keep in context window (older messages are trimmed)
MAX_HISTORY_MESSAGES = 40


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _to_lc_messages(stored: list[dict]) -> list:
    """Convert stored JSONB messages → LangChain message objects."""
    result = []
    for m in stored:
        role = m.get("role")
        content = m.get("content", "")
        if role == "human":
            result.append(HumanMessage(content=content))
        elif role == "ai":
            result.append(AIMessage(content=content))
        # Tool messages are context-only; skip them to avoid confusing the LLM
    return result


def _from_lc_message(msg) -> dict | None:
    """Convert a LangChain message → storable dict. Returns None for unsupported types."""
    now = datetime.utcnow().isoformat()
    if isinstance(msg, HumanMessage):
        return {"role": "human", "content": _extract_text(msg.content), "timestamp": now}
    if isinstance(msg, AIMessage):
        text = _extract_text(msg.content)
        if not text:  # pure tool-call message with no text — skip
            return None
        return {"role": "ai", "content": text, "timestamp": now}
    if isinstance(msg, ToolMessage):
        return {
            "role": "tool",
            "content": str(msg.content)[:2000],
            "timestamp": now,
            "tool_name": getattr(msg, "name", None),
        }
    return None


def _extract_text(content) -> str:
    """Extract plain text from LangChain message content (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


def _sse(event: str, data: dict) -> str:
    """Format a single SSE frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _load_user_context(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Load profile + preferences for the system prompt."""
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()

    prefs_result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user_id)
    )
    prefs = prefs_result.scalar_one_or_none()

    return {
        "user_skills": (profile.skills_technical or [])[:15] if profile else [],
        "target_roles": (prefs.target_roles or []) if prefs else [],
        "preferred_locations": (prefs.preferred_locations or []) if prefs else [],
        "has_cv": bool(profile and profile.cv_html_template),
    }


# ─── SSE Stream Generator ─────────────────────────────────────────────────────


async def _stream_chat(
    user: User,
    request_body: ChatRequest,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """
    Core generator: builds LangGraph state, streams events, persists thread.
    Yields raw SSE-formatted strings.
    """
    thread_id: uuid.UUID | None = request_body.thread_id
    thread: ChatThread | None = None

    try:
        # ── Load or create thread ─────────────────────────────────────────
        if thread_id:
            thread_result = await db.execute(
                select(ChatThread).where(
                    ChatThread.id == thread_id,
                    ChatThread.user_id == user.id,
                )
            )
            thread = thread_result.scalar_one_or_none()
            if not thread:
                yield _sse("error", {"message": "Thread introuvable."})
                return
        else:
            thread = ChatThread(user_id=user.id, messages=[])
            db.add(thread)
            await db.flush()
            await db.refresh(thread)
            thread_id = thread.id

        # ── Build history ────────────────────────────────────────────────
        history_messages = _to_lc_messages(thread.messages[-MAX_HISTORY_MESSAGES:])
        new_human_msg = HumanMessage(content=request_body.message)

        # Set thread title from first human message
        if not thread.title:
            thread.title = request_body.message[:80]

        # ── Load user context for system prompt ───────────────────────────
        ctx = await _load_user_context(db, user.id)

        initial_state = {
            "messages": history_messages + [new_human_msg],
            "user_id": str(user.id),
            "user_name": user.full_name,
            "thread_id": str(thread_id),
            **ctx,
        }

        # ── Compile graph ─────────────────────────────────────────────────
        graph = make_graph(db=db, user_id=user.id)

        # ── Stream events ─────────────────────────────────────────────────
        input_tokens_total = 0
        output_tokens_total = 0
        new_messages_to_save: list[dict] = []

        # Persist the user message immediately
        new_messages_to_save.append(
            {"role": "human", "content": request_body.message, "timestamp": datetime.utcnow().isoformat()}
        )

        async for event in graph.astream_events(initial_state, version="v2"):
            kind = event["event"]
            name = event.get("name", "")

            # ── Token streaming ───────────────────────────────────────────
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and chunk.content:
                    text = _extract_text(chunk.content)
                    if text:
                        yield _sse("token", {"text": text})

            # ── Tool start → status message ───────────────────────────────
            elif kind == "on_tool_start":
                tool_name = name
                status_msg = TOOL_STATUS.get(tool_name, f"⚙️ Exécution de {tool_name}...")
                yield _sse("status", {"message": status_msg, "tool": tool_name})

            # ── Tool end → summary + store in messages ────────────────────
            elif kind == "on_tool_end":
                tool_name = name
                output = event["data"].get("output", "")
                output_str = str(output)[:500]
                yield _sse("tool_end", {"tool": tool_name, "summary": output_str})
                new_messages_to_save.append(
                    {
                        "role": "tool",
                        "content": str(output)[:2000],
                        "timestamp": datetime.utcnow().isoformat(),
                        "tool_name": tool_name,
                    }
                )

            # ── LLM end → collect full AI message + token usage ───────────
            elif kind == "on_chat_model_end":
                response = event["data"].get("output")
                if response:
                    text = _extract_text(response.content)
                    if text:
                        new_messages_to_save.append(
                            {"role": "ai", "content": text, "timestamp": datetime.utcnow().isoformat()}
                        )
                    usage = getattr(response, "usage_metadata", None) or {}
                    input_tokens_total += usage.get("input_tokens", 0)
                    output_tokens_total += usage.get("output_tokens", 0)

        # ── Persist messages to thread ────────────────────────────────────
        thread.messages = list(thread.messages) + new_messages_to_save
        thread.total_input_tokens += input_tokens_total
        thread.total_output_tokens += output_tokens_total
        await db.commit()

        yield _sse("done", {"thread_id": str(thread_id)})

    except Exception as e:
        logger.error(f"[Chat] Stream error for user {user.id}: {e}", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        yield _sse("error", {"message": f"Erreur interne: {e}"})


# ─── Routes ───────────────────────────────────────────────────────────────────


@router.post("")
async def chat_stream(
    request: Request,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start or continue a conversation with Dr. Rousseau.
    Returns a Server-Sent Events stream.

    The client should listen for:
    - `status`   — tool execution progress
    - `token`    — incremental LLM text
    - `tool_end` — tool result summary
    - `done`     — conversation complete, includes thread_id
    - `error`    — error occurred
    """
    return StreamingResponse(
        _stream_chat(current_user, body, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@router.get("/threads", response_model=list[ChatThreadListItem])
async def list_threads(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all conversation threads for the current user, newest first."""
    result = await db.execute(
        select(ChatThread)
        .where(ChatThread.user_id == current_user.id)
        .order_by(ChatThread.updated_at.desc())
        .limit(50)
    )
    threads = result.scalars().all()
    return [
        ChatThreadListItem(
            id=t.id,
            title=t.title,
            message_count=len(t.messages),
            updated_at=t.updated_at,
        )
        for t in threads
    ]


@router.get("/threads/{thread_id}", response_model=ChatThreadOut)
async def get_thread(
    thread_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full message history for a thread."""
    result = await db.execute(
        select(ChatThread).where(
            ChatThread.id == thread_id,
            ChatThread.user_id == current_user.id,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread introuvable.")
    return ChatThreadOut(
        id=thread.id,
        title=thread.title,
        messages=[
            {
                "role": m["role"],
                "content": m["content"],
                "timestamp": m.get("timestamp", ""),
                "tool_name": m.get("tool_name"),
            }
            for m in thread.messages
        ],
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation thread."""
    result = await db.execute(
        select(ChatThread).where(
            ChatThread.id == thread_id,
            ChatThread.user_id == current_user.id,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread introuvable.")
    await db.delete(thread)
    await db.commit()
