"""
Text-to-SQL agent using Claude's tool-use loop.
Patterns: tool-use loop, self-correction on SQL errors, model routing, prompt caching.

Model routing (via router.py):
  Simple queries  -> MODEL_PRIMARY   (Haiku: fast, cheap)
  Complex queries -> MODEL_FALLBACK  (Sonnet: joins, rankings, subqueries)
  Escalation      -> MODEL_FALLBACK  (if Haiku has not finished within its turn budget)

Models and limits live in config.py.
"""
import logging
from functools import lru_cache
from typing import Callable, List, Optional

import anthropic

import config
from config import MODEL_FALLBACK, MODEL_PRIMARY  # re-exported for callers
from router import classify
from tools import TOOL_DEFINITIONS, execute_tool, get_schema_text, result_is_error
from verify import check_answer

log = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are an expert SQL analyst. Your job is to answer business questions by querying a DuckDB database.

Database schema (already loaded, so you do not need to call get_schema):
{schema}

TPC-H notes:
- Column names carry a table prefix: c_ customer, o_ orders, l_ lineitem, p_ part, s_ supplier, ps_ partsupp, n_ nation, r_ region.
- Join keys: orders.o_custkey = customer.c_custkey; lineitem.l_orderkey = orders.o_orderkey; lineitem.l_partkey = part.p_partkey; lineitem.l_suppkey = supplier.s_suppkey; partsupp(ps_partkey, ps_suppkey) links part and supplier; customer.c_nationkey and supplier.s_nationkey = nation.n_nationkey; nation.n_regionkey = region.r_regionkey.
- Revenue is SUM(l_extendedprice * (1 - l_discount)) over lineitem. o_totalprice is the order total.
- Order dates span 1992-1998. o_orderstatus is one of F, O, P. Dates are DATE type; use DATE '1995-01-01' syntax.

Workflow:
1. Write and execute SQL with run_sql. Use sample_table only if you need to see data formats or value ranges.
2. If the SQL returns an error, fix it and retry. You have up to {max_errors} failed attempts.
3. Once you have the results, provide a clear, concise answer to the business question.

Rules:
- Always use fully qualified column names (table.column) in JOINs.
- For monetary values, round to 2 decimal places in your answer.
- If the question asks for a number (count, sum, etc.), state the number clearly in your final answer.
- Questions may be follow-ups to earlier ones in this conversation; use the earlier context to resolve references like "and for 1996?".
- Do not explain the SQL unless asked. Focus on the answer.
- Write your final answer in plain conversational English. No markdown, no headers, no bullet points, no bold text, no emojis. Just write naturally as if you are speaking to someone.
"""


@lru_cache(maxsize=1)
def get_client() -> anthropic.Anthropic:
    """Created lazily so importing this module never needs an API key."""
    return anthropic.Anthropic()


@lru_cache(maxsize=1)
def get_system_blocks() -> list:
    """System prompt with the live schema embedded, marked cacheable."""
    text = SYSTEM_PROMPT_TEMPLATE.format(schema=get_schema_text(), max_errors=config.MAX_SQL_ERRORS)
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


class _Run:
    """Mutable state shared by the Haiku and Sonnet phases of one question."""

    def __init__(self, messages: list, temperature: Optional[float],
                 on_step: Optional[Callable[[dict], None]]):
        self.messages = messages
        self.temperature = temperature
        self.on_step = on_step
        self.steps = []  # type: List[dict]
        self.iterations = 0
        self.sql_errors = 0
        self.last_sql = None  # type: Optional[str]
        self.answer = ""
        self.usage = {}  # model -> {"input", "output", "cache_read", "cache_write"}

    def add_usage(self, model: str, u) -> None:
        d = self.usage.setdefault(model, {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0})
        d["input"] += getattr(u, "input_tokens", 0) or 0
        d["output"] += getattr(u, "output_tokens", 0) or 0
        d["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
        d["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0

    def usage_summary(self) -> dict:
        tokens = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}
        cost = 0.0
        for model, d in self.usage.items():
            tokens["input_tokens"] += d["input"]
            tokens["output_tokens"] += d["output"]
            tokens["cache_read_tokens"] += d["cache_read"]
            tokens["cache_write_tokens"] += d["cache_write"]
            price_in, price_out = config.MODEL_PRICING.get(model, (0.0, 0.0))
            cost += (
                d["input"] * price_in
                + d["cache_read"] * price_in * 0.1
                + d["cache_write"] * price_in * 1.25
                + d["output"] * price_out
            ) / 1e6
        return {**tokens, "cost_usd": round(cost, 6)}


def _run_loop(run: _Run, model: str, max_iterations: int) -> str:
    """
    Run the tool-use loop with one model until it answers or a budget is hit.
    Returns "done" | "max_tokens" | "max_iterations" | "sql_errors".
    """
    for _ in range(max_iterations):
        run.iterations += 1
        kwargs = dict(
            model=model,
            max_tokens=config.MAX_TOKENS,
            system=get_system_blocks(),
            tools=TOOL_DEFINITIONS,
            messages=run.messages,
        )
        if run.temperature is not None:
            kwargs["temperature"] = run.temperature
        response = get_client().messages.create(**kwargs)
        run.add_usage(model, response.usage)

        log.info("[iter %d] model=%s stop=%s", run.iterations, model, response.stop_reason)

        if response.stop_reason == "max_tokens":
            return "max_tokens"

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason == "end_turn" or not tool_calls:
            run.answer = "\n".join(b.text for b in response.content if b.type == "text").strip()
            return "done"

        run.messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tc in tool_calls:
            result = execute_tool(tc.name, tc.input)
            is_error = result_is_error(result)
            log.info("  %s(%s) -> %s", tc.name, list(tc.input.keys()), result[:200])

            if tc.name == "run_sql":
                run.last_sql = tc.input.get("query")
                if is_error:
                    run.sql_errors += 1

            step = {"tool": tc.name, "input": tc.input, "result": result}
            run.steps.append(step)
            if run.on_step:
                run.on_step(step)

            block = {"type": "tool_result", "tool_use_id": tc.id, "content": result}
            if is_error:
                block["is_error"] = True
            tool_results.append(block)
        run.messages.append({"role": "user", "content": tool_results})

        if run.sql_errors >= config.MAX_SQL_ERRORS:
            return "sql_errors"

    return "max_iterations"


_ERRORS = {
    "max_tokens": "The answer was cut off (token limit reached).",
    "max_iterations": "Max iterations reached without a final answer.",
    "sql_errors": f"Gave up after {config.MAX_SQL_ERRORS} failed SQL attempts.",
}


def _build_messages(question: str, history: Optional[List[dict]]) -> list:
    messages = []
    for turn in (history or [])[-config.MAX_HISTORY_TURNS:]:
        q, a = (turn.get("question") or "").strip(), (turn.get("answer") or "").strip()
        if q and a:
            messages.append({"role": "user", "content": q})
            messages.append({"role": "assistant", "content": a})
    messages.append({"role": "user", "content": question})
    return messages


def run_agent(
    question: str,
    max_iterations: int = config.MAX_ITERATIONS,
    history: Optional[List[dict]] = None,
    temperature: Optional[float] = None,
    on_step: Optional[Callable[[dict], None]] = None,
) -> dict:
    """
    Run the agent on a natural language question.

    Routing strategy (two layers):
      1. Proactive: router.classify() picks the starting model before any API call.
      2. Reactive:  if Haiku was chosen but hasn't finished in HAIKU_MAX_ITERS,
                    the same conversation is handed to Sonnet to complete.

    `history` is a list of {"question", "answer"} dicts for follow-up questions.
    `on_step` is called with each tool step as it completes (used for streaming).

    Returns {"answer", "sql", "iterations", "error", "model", "model_label", "routed_to",
             "steps", "usage", "cost_usd", "answer_check"}
    """
    run = _Run(_build_messages(question, history), temperature, on_step)

    routed_to = classify(question)
    model = MODEL_PRIMARY if routed_to == "haiku" else MODEL_FALLBACK
    log.info("[router] %r -> %s (%s)", question[:60], routed_to, model)

    if model == MODEL_PRIMARY:
        status = _run_loop(run, model, min(config.HAIKU_MAX_ITERS, max_iterations))
        if status not in ("done", "sql_errors") and run.iterations < max_iterations:
            log.info("[escalating to %s after %d Haiku iterations]", MODEL_FALLBACK, run.iterations)
            model = MODEL_FALLBACK
            status = _run_loop(run, model, max_iterations - run.iterations)
    else:
        status = _run_loop(run, model, max_iterations)

    usage = run.usage_summary()
    error = None if status == "done" else _ERRORS[status]
    return {
        "answer": run.answer if status == "done" else "",
        "sql": run.last_sql,
        "iterations": run.iterations,
        "error": error,
        "model": model,
        "model_label": config.model_label(model),
        "routed_to": routed_to,
        "steps": run.steps,
        "usage": {k: v for k, v in usage.items() if k != "cost_usd"},
        "cost_usd": usage["cost_usd"],
        "answer_check": check_answer(run.answer, run.steps) if status == "done" else None,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for q in [
        "How many customers are in the database?",
        "What are the top 3 nations by number of customers?",
    ]:
        result = run_agent(q)
        print(f"\nAnswer:     {result['answer']}")
        print(f"SQL:        {result['sql']}")
        print(f"Iterations: {result['iterations']}")
        print(f"Model:      {result['model_label']} (routed to: {result['routed_to']})")
        print(f"Cost:       ${result['cost_usd']:.4f}")
        print()
