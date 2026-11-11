import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import config
from agent import run_agent
from db_setup import DatabaseNotReady

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")

app = FastAPI(title="Text-to-SQL Analyst")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ── Models ────────────────────────────────────────────────────────────────────

class Turn(BaseModel):
    question: str = Field(max_length=config.MAX_QUESTION_CHARS)
    answer: str = Field(max_length=4000)


class Question(BaseModel):
    question: str = Field(max_length=config.MAX_QUESTION_CHARS)
    history: List[Turn] = Field(default_factory=list, max_length=config.MAX_HISTORY_TURNS * 2)


# ── Rate limiting (in-memory, per client IP; fine for a single process) ──────

_hits = defaultdict(deque)  # type: Dict[str, Deque[float]]


def _check_rate_limit(request: Request) -> None:
    if config.RATE_LIMIT_PER_MIN <= 0:
        return
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= config.RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a moment and try again.")
    q.append(now)


def _prepare(body: Question, request: Request):
    _check_rate_limit(request)
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    history = [t.model_dump() for t in body.history]
    return question, history


def _public_error(e: Exception) -> str:
    """Log the real error, return a message that is safe to show to the client."""
    log.exception("Agent request failed")
    if isinstance(e, DatabaseNotReady):
        return "The database has not been set up yet. Run `python db_setup.py` on the server."
    if isinstance(e, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return "The server's Anthropic API key is missing or invalid."
    if isinstance(e, anthropic.RateLimitError):
        return "The language model is rate limited. Please try again shortly."
    if isinstance(e, anthropic.APIError):
        return "The language model request failed. Please try again."
    return "Something went wrong while answering your question."


def _status_for(e: Exception) -> int:
    if isinstance(e, DatabaseNotReady):
        return 503
    if isinstance(e, anthropic.APIError):
        return 502
    return 500


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/config")
async def get_config():
    return {"suggestions": config.SUGGESTIONS}


@app.post("/ask")
async def ask(body: Question, request: Request):
    question, history = _prepare(body, request)
    try:
        # run_agent is synchronous and slow; keep it off the event loop.
        return await run_in_threadpool(run_agent, question, history=history)
    except Exception as e:
        raise HTTPException(status_code=_status_for(e), detail=_public_error(e))


@app.post("/ask/stream")
async def ask_stream(body: Question, request: Request):
    """Server-sent events: `step` per tool call, then `result` (or `error`)."""
    question, history = _prepare(body, request)
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()  # type: asyncio.Queue

    def emit(event: str, data) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, (event, data))

    def worker() -> None:
        try:
            result = run_agent(question, history=history, on_step=lambda s: emit("step", s))
            emit("result", result)
        except Exception as e:
            emit("error", {"detail": _public_error(e)})
        finally:
            emit("done", None)

    loop.run_in_executor(None, worker)

    async def events():
        while True:
            event, data = await queue.get()
            if event == "done":
                break
            yield f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
