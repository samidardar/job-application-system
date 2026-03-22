"""
Dr. Rousseau Career Consultant — API router.

Endpoints:
  POST   /consultant/conversations                         — create conversation
  GET    /consultant/conversations                         — list conversations
  GET    /consultant/conversations/{id}/messages           — get message history
  POST   /consultant/conversations/{id}/chat               — send message (SSE stream)
  DELETE /consultant/conversations/{id}                    — delete conversation

SSE streaming: POST /conversations/{id}/chat returns text/event-stream.
Use fetch() + ReadableStream on the frontend (EventSource doesn't support POST).
"""
import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel, Field
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db, AsyncSessionLocal
from app.models.conversation import Conversation, Message
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/consultant", tags=["consultant"])

# ─── Request / Response Schemas ──────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    last_message_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Helpers ─────────────────────────────────────────────────────────────────


async def _get_conv_or_404(
    conversation_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


async def _load_messages(
    conversation_id: uuid.UUID, db: AsyncSession
) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())


def _to_langchain_messages(messages: list[Message]):
    """Convert DB messages to LangChain message objects."""
    lc = []
    for m in messages:
        if m.role == "user":
            lc.append(HumanMessage(content=m.content))
        else:
            lc.append(AIMessage(content=m.content))
    return lc


def _auto_title(message: str) -> str:
    """Generate a short conversation title from the first user message."""
    title = message.strip().replace("\n", " ")
    return title[:80].rstrip() + ("…" if len(title) > 80 else "")


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new blank conversation."""
    conv = Conversation(
        user_id=current_user.id,
        title="Nouvelle conversation",
        created_at=datetime.utcnow(),
        last_message_at=datetime.utcnow(),
    )
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's conversations, most recent first."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.last_message_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def get_messages(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full message history for a conversation."""
    await _get_conv_or_404(conversation_id, current_user.id, db)
    messages = await _load_messages(conversation_id, db)
    return messages


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation and all its messages (CASCADE)."""
    await _get_conv_or_404(conversation_id, current_user.id, db)
    await db.execute(
        delete(Conversation).where(Conversation.id == conversation_id)
    )
    # No explicit return — 204 No Content


@router.post("/conversations/{conversation_id}/chat")
async def chat_stream(
    conversation_id: uuid.UUID,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a user message and stream Dr. Rousseau's reply via Server-Sent Events.

    Response format: text/event-stream
      data: {"chunk": "..."}          — token-by-token text chunks
      data: {"event": "done", "message_id": "..."}  — stream complete
      data: {"event": "error", "message": "..."}    — unrecoverable error
    """
    # ── Validate conversation ownership ──────────────────────────────────────
    conv = await _get_conv_or_404(conversation_id, current_user.id, db)

    # ── Save user message ─────────────────────────────────────────────────────
    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=body.message.strip(),
        created_at=datetime.utcnow(),
    )
    db.add(user_msg)

    # Auto-set title from first real message
    if conv.title == "Nouvelle conversation":
        conv.title = _auto_title(body.message)

    await db.commit()

    # ── Load full history (including the message we just saved) ───────────────
    history = await _load_messages(conversation_id, db)
    lc_messages = _to_langchain_messages(history)

    # ── Stream generator ──────────────────────────────────────────────────────
    # Use a separate DB session inside the generator — the DI session above
    # is already committed and will be closed after the route handler returns.

    async def generate():
        from app.agents.consultant_graph import get_consultant_graph
        graph = get_consultant_graph()

        full_response = ""
        assistant_msg_id = str(uuid.uuid4())

        async with AsyncSessionLocal() as stream_db:
            try:
                state = {"messages": lc_messages}

                async for event in graph.astream_events(state, version="v2"):
                    kind = event.get("event", "")
                    if kind == "on_chat_model_stream":
                        chunk = event["data"].get("chunk")
                        if chunk is None:
                            continue
                        # Gemini content can be str or list[dict]
                        content = chunk.content
                        if isinstance(content, list):
                            content = "".join(
                                c.get("text", "") if isinstance(c, dict) else str(c)
                                for c in content
                            )
                        if content:
                            full_response += content
                            yield f"data: {json.dumps({'chunk': content})}\n\n"

                # Persist assistant message
                if not full_response:
                    full_response = "Je suis désolé, je n'ai pas pu générer une réponse. Veuillez réessayer."

                assistant_msg = Message(
                    id=uuid.UUID(assistant_msg_id),
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_response,
                    created_at=datetime.utcnow(),
                )
                stream_db.add(assistant_msg)

                await stream_db.execute(
                    update(Conversation)
                    .where(Conversation.id == conversation_id)
                    .values(last_message_at=datetime.utcnow())
                )
                await stream_db.commit()

                yield f"data: {json.dumps({'event': 'done', 'message_id': assistant_msg_id})}\n\n"

            except RuntimeError as e:
                # Config errors (missing API key, token budget)
                logger.error(f"Consultant config error: {e}")
                await stream_db.rollback()
                yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

            except Exception as e:
                logger.error(f"Consultant stream error for conv {conversation_id}: {e}", exc_info=True)
                await stream_db.rollback()
                yield (
                    f"data: {json.dumps({'event': 'error', 'message': 'Une erreur est survenue. Veuillez réessayer.'})}\n\n"
                )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
        },
    )
