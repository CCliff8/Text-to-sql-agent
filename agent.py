"""
Text-to-SQL agent using Claude's tool-use loop.
Patterns: tool-use loop, self-correction on SQL errors, model routing.

Model routing (via router.py):
  Simple queries  → claude-haiku-4-5   (fast, cheap)
  Complex queries → claude-sonnet-5-5  (smarter, for joins/rankings/subqueries)
  Fallback        → claude-sonnet-5-5  (if Haiku fails within its turn budget)
"""
from dotenv import load_dotenv
load_dotenv()

import anthropic
from typing import Optional
from tools import TOOL_DEFINITIONS, execute_tool
from router import classify

client = anthropic.Anthropic()

MODEL_PRIMARY  = "claude-haiku-4-5-20251001"
MODEL_FALLBACK = "claude-sonnet-4-6"
HAIKU_MAX_ITERS = 3  # reactive fallback: escalate if Haiku hasn't finished

SYSTEM_PROMPT = """You are an expert SQL analyst. Your job is to answer business questions by querying a DuckDB database.

Workflow:
1. Call get_schema to understand available tables and columns (always do this first unless you already know the schema).
2. If needed, call sample_table to understand data formats and value ranges.
3. Write and execute SQL with run_sql.
4. If the SQL returns an error, fix it and retry. You have up to 5 attempts.
5. Once you have the results, provide a clear, concise answer to the business question.

Rules:
- Always use fully qualified column names (table.column) in JOINs.
- TPC-H dates are stored as DATE type; use DATE '2025-01-01' syntax.
- For monetary values, round to 2 decimal places in your answer.
- If the question asks for a number (count, sum, etc.), state the number clearly in your final answer.
- Do not explain the SQL unless asked. Focus on the answer.
- Write your final answer in plain conversational English. No markdown, no headers, no bullet points, no bold text, no emojis. Just write naturally as if you are speaking to someone.
"""


def _run_loop(
    messages: list,
    model: str,
    max_iterations: int,
    verbose: bool,
    iteration_offset: int = 0,
):
    """
    Run the tool-use loop with a given model.
    Returns (messages, last_sql, iterations_used, finished, answer).
    """
    last_sql = None
    iterations = 0
    steps = []  # [(tool_name, input_summary, result_summary)]

    for _ in range(max_iterations):
        iterations += 1
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        if verbose:
            print(f"\n[iter {iteration_offset + iterations}] model={model} stop={response.stop_reason}")

        tool_calls = []
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(block)
                if block.name == "run_sql":
                    last_sql = block.input.get("query")
                if verbose:
                    print(f"  → {block.name}({list(block.input.keys())})")

        if response.stop_reason == "end_turn" or not tool_calls:
            answer = "\n".join(text_parts).strip()
            return messages, last_sql, iterations, True, answer, steps

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tc in tool_calls:
            result = execute_tool(tc.name, tc.input)
            if verbose:
                print(f"  ← {tc.name}: {result[:200]}{'...' if len(result) > 200 else ''}")
            steps.append({
                "tool": tc.name,
                "input": tc.input,
                "result": result,
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result,
            })
        messages.append({"role": "user", "content": tool_results})

    return messages, last_sql, iterations, False, "", steps


def run_agent(question: str, max_iterations: int = 10, verbose: bool = False) -> dict:
    """
    Run the agent on a natural language question.

    Routing strategy (two layers):
      1. Proactive: router.classify() picks the starting model before any API call.
      2. Reactive:  if Haiku was chosen but hasn't finished in HAIKU_MAX_ITERS,
                    the same conversation is handed to Sonnet to complete.

    Returns {"answer": str, "sql": str | None, "iterations": int,
             "error": str | None, "model": str, "routed_to": str}
    """
    messages = [{"role": "user", "content": question}]

    # --- Proactive routing ---
    routed_to = classify(question)
    start_model = MODEL_PRIMARY if routed_to == "haiku" else MODEL_FALLBACK

    if verbose:
        print(f"\n[router] '{question[:60]}...' → {routed_to} ({start_model})")

    # --- Phase 1: chosen model ---
    phase1_limit = HAIKU_MAX_ITERS if start_model == MODEL_PRIMARY else max_iterations
    messages, last_sql, p1_iters, finished, answer, steps = _run_loop(
        messages=messages,
        model=start_model,
        max_iterations=min(phase1_limit, max_iterations),
        verbose=verbose,
        iteration_offset=0,
    )

    if finished:
        return {
            "answer": answer,
            "sql": last_sql,
            "iterations": p1_iters,
            "error": None,
            "model": start_model,
            "routed_to": routed_to,
            "steps": steps,
        }

    # --- Phase 2: reactive fallback to Sonnet (only if Phase 1 was Haiku) ---
    if start_model == MODEL_FALLBACK:
        return {
            "answer": "",
            "sql": last_sql,
            "iterations": p1_iters,
            "error": "Max iterations reached without a final answer.",
            "model": MODEL_FALLBACK,
            "routed_to": routed_to,
            "steps": steps,
        }

    if verbose:
        print(f"\n[escalating to {MODEL_FALLBACK} after {p1_iters} Haiku iterations]")

    remaining = max_iterations - p1_iters
    messages, last_sql_s, p2_iters, finished, answer, steps2 = _run_loop(
        messages=messages,
        model=MODEL_FALLBACK,
        max_iterations=remaining,
        verbose=verbose,
        iteration_offset=p1_iters,
    )

    total_iters = p1_iters + p2_iters
    final_sql = last_sql_s or last_sql

    if finished:
        return {
            "answer": answer,
            "sql": final_sql,
            "iterations": total_iters,
            "error": None,
            "model": MODEL_FALLBACK,
            "routed_to": routed_to,
            "steps": steps + steps2,
        }

    return {
        "answer": "",
        "sql": final_sql,
        "iterations": total_iters,
        "error": "Max iterations reached without a final answer.",
        "model": MODEL_FALLBACK,
        "routed_to": routed_to,
        "steps": steps + steps2,
    }


if __name__ == "__main__":
    questions = [
        "How many customers are in the database?",
        "What are the top 3 nations by number of customers?",
    ]
    for q in questions:
        result = run_agent(q, verbose=True)
        print(f"\nAnswer:     {result['answer']}")
        print(f"SQL:        {result['sql']}")
        print(f"Iterations: {result['iterations']}")
        print(f"Model:      {result['model']} (routed to: {result['routed_to']})")
        print()
