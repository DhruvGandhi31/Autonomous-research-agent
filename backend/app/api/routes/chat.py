import asyncio
import json
import threading
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import AsyncGenerator, Optional

import ollama
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from config.settings import settings
from core.agent import research_agent
from core.memory import memory_manager
from services.chat_service import ChatMessage, chat_service

router = APIRouter()

SYSTEM_PROMPT = """You are a highly capable research assistant. You help users understand complex topics, analyze documents and images, and conduct in-depth research. When users share document or image content, analyze it carefully and provide detailed insights.

Use markdown formatting for clarity (headers, bullet points, code blocks). Be concise yet thorough. When you don't know something, say so honestly."""


# ─────────────────────────── Request / Response models ─────────────────────────────

class AttachmentIn(BaseModel):
    name: str
    file_type: str
    extracted_text: str
    description: str = ""
    size: int = 0


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=32_000)
    attachments: list[AttachmentIn] = Field(default_factory=list)
    trigger_research: bool = False


class CreateSessionRequest(BaseModel):
    title: str = "New Chat"
    mode: str = "chat"  # "chat" | "research"


class RenameSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)


# ─────────────────────────── Streaming helper ──────────────────────────────────────

async def _stream_ollama(messages: list[dict]) -> AsyncGenerator[str, None]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def run_sync():
        try:
            client = ollama.Client(host=settings.ollama_base_url)
            for chunk in client.chat(
                model=settings.default_model, messages=messages, stream=True
            ):
                content = chunk["message"]["content"]
                if content:
                    loop.call_soon_threadsafe(queue.put_nowait, content)
        except Exception as e:
            logger.error(f"LLM stream error: {e}")
            loop.call_soon_threadsafe(
                queue.put_nowait, f"\n\n*Error communicating with LLM: {e}*"
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    thread = threading.Thread(target=run_sync, daemon=True)
    thread.start()

    while True:
        item = await queue.get()
        if item is None:
            break
        yield item


# ─────────────────────────── Session endpoints ─────────────────────────────────────

@router.post("/sessions")
async def create_session(req: CreateSessionRequest):
    session = chat_service.create_session(title=req.title, mode=req.mode)
    return asdict(session)


@router.get("/sessions")
async def list_sessions():
    sessions = chat_service.list_sessions()
    return {
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "mode": s.mode,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "message_count": len(s.messages),
                "last_message": s.messages[-1].content[:80] if s.messages else None,
            }
            for s in sessions
        ],
        "total": len(sessions),
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    session = chat_service.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return asdict(session)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    if not chat_service.delete_session(session_id):
        raise HTTPException(404, "Session not found")
    return {"message": "Session deleted"}


@router.patch("/sessions/{session_id}/rename")
async def rename_session(session_id: str, req: RenameSessionRequest):
    if not chat_service.rename_session(session_id, req.title):
        raise HTTPException(404, "Session not found")
    return {"message": "Session renamed"}


# ─────────────────────────── Message streaming endpoint ────────────────────────────

@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    req: SendMessageRequest,
    background_tasks: BackgroundTasks,
):
    session = chat_service.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    # Save user message
    user_msg = ChatMessage(
        id=str(uuid.uuid4()),
        role="user",
        content=req.content,
        timestamp=datetime.now().isoformat(),
        attachments=[a.model_dump() for a in req.attachments],
    )
    chat_service.add_message(session_id, user_msg)

    # Research mode: kick off research pipeline
    if session.mode == "research" or req.trigger_research:
        return await _handle_research_stream(
            session_id, req.content, background_tasks
        )

    # Build message history for LLM
    history = chat_service.get_conversation_history(session_id, limit=20)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    assistant_msg_id = str(uuid.uuid4())

    async def generate():
        full_content = ""
        try:
            async for chunk in _stream_ollama(messages):
                full_content += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
        except Exception as e:
            err_msg = f"\n\n*Stream error: {e}*"
            full_content += err_msg
            yield f"data: {json.dumps({'type': 'chunk', 'content': err_msg})}\n\n"

        assistant_msg = ChatMessage(
            id=assistant_msg_id,
            role="assistant",
            content=full_content,
            timestamp=datetime.now().isoformat(),
        )
        chat_service.add_message(session_id, assistant_msg)
        yield f"data: {json.dumps({'type': 'done', 'message': asdict(assistant_msg)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _handle_research_stream(
    session_id: str, topic: str, background_tasks: BackgroundTasks
):
    research_id = f"research_{uuid.uuid4().hex[:12]}"
    requirements = {"max_sources": 10, "include_academic": True, "include_analysis": True}

    await memory_manager.store_context(
        research_id,
        {
            "topic": topic,
            "requirements": requirements,
            "status": "queued",
            "started_at": datetime.now().isoformat(),
            "research_id": research_id,
        },
    )

    background_tasks.add_task(
        research_agent.conduct_research, topic, requirements, research_id
    )

    assistant_msg = ChatMessage(
        id=str(uuid.uuid4()),
        role="assistant",
        content=f"Starting research on **{topic}**... This will take a moment.",
        timestamp=datetime.now().isoformat(),
        research_id=research_id,
    )
    chat_service.add_message(session_id, assistant_msg)

    async def generate():
        yield f"data: {json.dumps({'type': 'research_started', 'research_id': research_id, 'topic': topic})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'message': asdict(assistant_msg)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
