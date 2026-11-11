import json

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

import api
import config
from db_setup import DatabaseNotReady

RESULT = {
    "answer": "Four.", "sql": "SELECT 4", "iterations": 1, "error": None, "model": "m", "model_label": "M",
    "routed_to": "haiku", "steps": [], "usage": {}, "cost_usd": 0.0, "answer_check": None,
}


@pytest.fixture
def client(monkeypatch):
    api._hits.clear()
    monkeypatch.setattr(api, "run_agent", lambda q, history=None, on_step=None, **kw: dict(RESULT, answer=f"echo:{q}:{len(history or [])}"))
    return TestClient(api.app)


def test_health_and_config(client):
    assert client.get("/health").json() == {"status": "ok"}
    suggestions = client.get("/config").json()["suggestions"]
    assert suggestions and {"label", "q"} <= set(suggestions[0])


def test_ask(client):
    r = client.post("/ask", json={"question": "  hi  "})
    assert r.status_code == 200 and r.json()["answer"] == "echo:hi:0"


def test_ask_with_history(client):
    r = client.post("/ask", json={"question": "and?", "history": [{"question": "a", "answer": "b"}]})
    assert r.json()["answer"] == "echo:and?:1"


def test_validation(client):
    assert client.post("/ask", json={"question": "   "}).status_code == 400
    assert client.post("/ask", json={"question": "x" * (config.MAX_QUESTION_CHARS + 1)}).status_code == 422
    assert client.post("/ask", json={}).status_code == 422
    too_long = [{"question": "q", "answer": "a"}] * (config.MAX_HISTORY_TURNS * 2 + 1)
    assert client.post("/ask", json={"question": "x", "history": too_long}).status_code == 422


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MIN", 2)
    codes = [client.post("/ask", json={"question": "x"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_errors_do_not_leak_internals(monkeypatch):
    api._hits.clear()

    def boom(*a, **kw):
        raise RuntimeError("secret internal detail /Users/me/key")
    monkeypatch.setattr(api, "run_agent", boom)
    r = TestClient(api.app).post("/ask", json={"question": "x"})
    assert r.status_code == 500 and "secret" not in r.text


@pytest.mark.parametrize("exc, status, fragment", [
    (DatabaseNotReady("x"), 503, "db_setup.py"),
    (anthropic.APIConnectionError(request=httpx.Request("POST", "http://x")), 502, "language model"),
])
def test_error_mapping(monkeypatch, exc, status, fragment):
    api._hits.clear()

    def boom(*a, **kw):
        raise exc
    monkeypatch.setattr(api, "run_agent", boom)
    r = TestClient(api.app).post("/ask", json={"question": "x"})
    assert r.status_code == status and fragment in r.json()["detail"]


def _events(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(l.split(": ", 1) for l in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_stream_emits_steps_then_result(monkeypatch):
    api._hits.clear()

    def fake(q, history=None, on_step=None, **kw):
        on_step({"tool": "run_sql", "input": {"query": "SELECT 1"}, "result": "{}"})
        return dict(RESULT)
    monkeypatch.setattr(api, "run_agent", fake)
    r = TestClient(api.app).post("/ask/stream", json={"question": "x"})
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _events(r.text)
    assert [e for e, _ in events] == ["step", "result"]
    assert events[0][1]["tool"] == "run_sql" and events[1][1]["answer"] == "Four."


def test_stream_reports_errors_as_events(monkeypatch):
    api._hits.clear()

    def boom(*a, **kw):
        raise RuntimeError("secret")
    monkeypatch.setattr(api, "run_agent", boom)
    r = TestClient(api.app).post("/ask/stream", json={"question": "x"})
    events = _events(r.text)
    assert events == [("error", {"detail": "Something went wrong while answering your question."})]
