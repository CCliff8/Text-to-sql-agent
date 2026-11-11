"""
Central configuration: models, limits, pricing and UI suggestions.

Imported by every other module, so `.env` is loaded exactly once, here.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# ── Models ────────────────────────────────────────────────────────────────────
# Override with HAIKU_MODEL / SONNET_MODEL in .env to try other versions.
MODEL_PRIMARY = os.getenv("HAIKU_MODEL", "claude-haiku-4-5-20251001")
MODEL_FALLBACK = os.getenv("SONNET_MODEL", "claude-sonnet-4-6")

MODEL_LABELS = {
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-sonnet-5-5": "Sonnet 5.5",
}

# USD per million tokens: (input, output). Cache reads cost 0.1x input, writes 1.25x.
# Estimates only; check https://www.anthropic.com/pricing for current rates.
MODEL_PRICING = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-5-5": (3.00, 15.00),
}


def model_label(model: str) -> str:
    return MODEL_LABELS.get(model, model)


# ── Agent limits ──────────────────────────────────────────────────────────────
MAX_TOKENS = 4096
MAX_ITERATIONS = 10        # total tool-use turns per question
HAIKU_MAX_ITERS = 4        # schema is in the prompt: run_sql -> (fix) -> answer fits comfortably
MAX_SQL_ERRORS = 5         # failed run_sql calls before giving up (matches the system prompt)
MAX_HISTORY_TURNS = 5      # previous Q&A pairs sent along for follow-up questions

# ── Database limits ───────────────────────────────────────────────────────────
MAX_ROWS = 100             # rows returned to the model / UI per query
QUERY_TIMEOUT_S = float(os.getenv("QUERY_TIMEOUT_S", "15"))
DUCKDB_MEMORY_LIMIT = os.getenv("DUCKDB_MEMORY_LIMIT", "1GB")
DUCKDB_THREADS = int(os.getenv("DUCKDB_THREADS", "2"))

# ── API ───────────────────────────────────────────────────────────────────────
MAX_QUESTION_CHARS = 500
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))  # 0 disables
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

# ── UI ────────────────────────────────────────────────────────────────────────
SUGGESTIONS = [
    {"label": "Top 3 nations by customers", "q": "What are the top 3 nations by number of customers?"},
    {"label": "Revenue by region", "q": "What is the total revenue by region?"},
    {"label": "Biggest customers", "q": "Who are the top 5 customers by total order value?"},
]
