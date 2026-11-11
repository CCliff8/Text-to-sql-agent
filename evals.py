"""
Evaluation framework for the Text-to-SQL agent.

A case passes when BOTH checks hold (the execution check only applies to cases with gold_sql):
  1. Answer check  - the final text matches the expected answer (see match types below).
  2. Execution check - at least one successful SQL query the agent ran returns the same
     rows as a gold query (order-insensitive, numbers within 0.5%, extra columns allowed).
     This catches answers that match the expected text by coincidence.

Match types:
  numeric_exact   - answer contains this exact number
  numeric_fuzzy   - answer contains a number within tolerance_pct % of expected (default 5)
  numeric_any     - answer contains any number (sanity check)
  contains_string - answer contains this string (case_insensitive optional)
  contains_any    - answer contains at least one string from options
  contains_all    - answer contains every string in options
  regex           - answer matches this regular expression

Usage:
  python evals.py                      # all cases, 4 parallel workers, temperature 0
  python evals.py q001 q002            # specific cases
  python evals.py --runs 3             # repeat each case to measure variance
  python evals.py --workers 1 -v       # sequential, verbose
"""
import argparse
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from agent import run_agent
from tools import run_query

CASES_PATH = os.path.join(os.path.dirname(__file__), "test_cases.json")
RESULTS_DIR = os.path.dirname(__file__)


# ── Answer matching ───────────────────────────────────────────────────────────

def _extract_numbers(text: str) -> List[float]:
    """Extract all numbers from text (handles commas in numbers)."""
    cleaned = text.replace(",", "")
    return [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", cleaned)]


def _passes(result_answer: str, case: dict) -> bool:
    answer = result_answer.strip()
    match_type = case["match_type"]
    expected = str(case["expected_answer"])
    ci = case.get("case_insensitive", False)

    if match_type == "numeric_exact":
        target = float(expected.replace(",", ""))
        return any(abs(n - target) < 0.5 for n in _extract_numbers(answer))

    if match_type == "numeric_fuzzy":
        numbers = _extract_numbers(answer)
        target = float(expected.replace(",", ""))
        tol = case.get("tolerance_pct", 5) / 100.0
        if target == 0:
            return any(abs(n) < 1 for n in numbers)
        return any(abs(n - target) / abs(target) <= tol for n in numbers)

    if match_type == "numeric_any":
        return len(_extract_numbers(answer)) > 0

    if match_type == "contains_string":
        return expected.lower() in answer.lower() if ci else expected in answer

    if match_type in ("contains_any", "contains_all"):
        options = case.get("options", [expected])
        if ci:
            answer, options = answer.lower(), [o.lower() for o in options]
        hit = any if match_type == "contains_any" else all
        return hit(o in answer for o in options)

    if match_type == "regex":
        return re.search(expected, answer, re.IGNORECASE if ci else 0) is not None

    return False


# ── Execution matching ────────────────────────────────────────────────────────

def _cells_equal(a, b) -> bool:
    num = (int, float)
    if isinstance(a, num) and isinstance(b, num) and not isinstance(a, bool) and not isinstance(b, bool):
        return math.isclose(a, b, rel_tol=5e-3, abs_tol=0.051)
    return str(a).strip().lower() == str(b).strip().lower()


def _row_contains(agent_row: list, gold_row: list) -> bool:
    """Every gold cell is present in the agent row (distinct cells, any column order)."""
    remaining = list(agent_row)
    for g in gold_row:
        for i, a in enumerate(remaining):
            if _cells_equal(a, g):
                del remaining[i]
                break
        else:
            return False
    return True


def rows_match(gold_rows: List[list], agent_rows: List[list]) -> bool:
    """Same number of rows, each gold row matched by a distinct agent row. Order-insensitive."""
    if len(gold_rows) != len(agent_rows):
        return False
    unused = list(agent_rows)
    for g in gold_rows:
        for i, a in enumerate(unused):
            if _row_contains(a, g):
                del unused[i]
                break
        else:
            return False
    return True


def _step_rows(step: dict) -> Optional[List[list]]:
    try:
        data = json.loads(step["result"])
    except (KeyError, ValueError):
        return None
    if "error" in data or "rows" not in data:
        return None
    return [list(r.values()) for r in data["rows"]]


def execution_match(case: dict, steps: list) -> Optional[bool]:
    """None if the case has no gold_sql, else whether any agent query matched any gold query."""
    gold = case.get("gold_sql")
    if not gold:
        return None
    gold_results = []
    for sql in gold if isinstance(gold, list) else [gold]:
        res = run_query(sql, max_rows=1000)
        if "error" not in res:
            gold_results.append([list(r.values()) for r in res["rows"]])
    agent_results = [r for r in (_step_rows(s) for s in steps if s.get("tool") == "run_sql") if r is not None]
    return any(rows_match(g, a) for g in gold_results for a in agent_results)


# ── Eval runner ───────────────────────────────────────────────────────────────

def _run_case(case: dict, run_idx: int, temperature: float) -> dict:
    base = {
        "id": case["id"],
        "run": run_idx,
        "category": case["category"],
        "question": case["question"],
        "expected": case["expected_answer"],
    }
    start = time.time()
    try:
        r = run_agent(case["question"], temperature=temperature)
        answer_ok = _passes(r["answer"], case)
        exec_ok = execution_match(case, r["steps"])
        return {
            **base,
            "answer": r["answer"],
            "sql": r["sql"],
            "answer_ok": answer_ok,
            "exec_ok": exec_ok,
            "passed": answer_ok and exec_ok is not False,
            "elapsed_s": round(time.time() - start, 2),
            "iterations": r["iterations"],
            "model": r["model"],
            "routed_to": r["routed_to"],
            "cost_usd": r["cost_usd"],
            "input_tokens": r["usage"]["input_tokens"],
            "output_tokens": r["usage"]["output_tokens"],
            "error": r["error"],
        }
    except Exception as e:
        return {
            **base, "answer": "", "sql": None, "answer_ok": False, "exec_ok": None, "passed": False,
            "elapsed_s": round(time.time() - start, 2), "iterations": 0, "model": "", "routed_to": "",
            "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "error": f"{type(e).__name__}: {e}",
        }


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} = {n / d:.0%}" if d else "n/a"


def run_evals(
    case_ids: Optional[List[str]] = None,
    verbose: bool = False,
    save_results: bool = True,
    workers: int = 4,
    runs: int = 1,
    temperature: float = 0.0,
) -> dict:
    """Run the evaluation suite. Returns a summary dict with accuracy, cost and routing metrics."""
    with open(CASES_PATH) as f:
        cases = json.load(f)["cases"]
    if case_ids:
        cases = [c for c in cases if c["id"] in case_ids]

    jobs = [(c, i) for c in cases for i in range(runs)]
    print(f"\n{'=' * 60}\nRunning {len(cases)} cases x {runs} run(s), {workers} worker(s), temperature {temperature}\n{'=' * 60}\n")

    started = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_run_case, c, i, temperature) for c, i in jobs]
        for n, fut in enumerate(futures, 1):
            r = fut.result()
            results.append(r)
            tag = "PASS" if r["passed"] else "FAIL"
            print(f"[{n:02d}/{len(jobs)}] {r['id']} run{r['run']} {tag} ({r['elapsed_s']:.1f}s, {r['iterations']} iters, ${r['cost_usd']:.4f}) {r['routed_to']}")
            if not r["passed"]:
                print(f"    Q: {r['question'][:90]}")
                print(f"    Expected: {r['expected']}   answer_ok={r['answer_ok']} exec_ok={r['exec_ok']}")
                print(f"    Got:      {(r['answer'] or r['error'] or '')[:150]}")
            elif verbose:
                print(f"    {r['answer'][:150]}")
    wall = time.time() - started

    total = len(results)
    passed = sum(r["passed"] for r in results)
    accuracy = passed / total if total else 0
    avg_time = sum(r["elapsed_s"] for r in results) / total if total else 0
    total_cost = sum(r["cost_usd"] for r in results)

    by_category = {}
    by_route = {}
    for r in results:
        for table, key in ((by_category, r["category"]), (by_route, r["routed_to"] or "error")):
            s = table.setdefault(key, {"total": 0, "passed": 0, "cost_usd": 0.0})
            s["total"] += 1
            s["passed"] += r["passed"]
            s["cost_usd"] += r["cost_usd"]

    # Cases that passed some runs but not others (only meaningful with --runs > 1).
    flaky = sorted({r["id"] for r in results if r["passed"]} & {r["id"] for r in results if not r["passed"]})

    print(f"\n{'=' * 60}")
    print(f"OVERALL ACCURACY: {_pct(passed, total)}")
    print(f"Avg time per question: {avg_time:.1f}s   (wall clock {wall:.0f}s)")
    print(f"Total cost: ${total_cost:.4f}   (${total_cost / total:.4f} per question)" if total else "")
    print("\nBy category:")
    for cat, s in sorted(by_category.items()):
        print(f"  {cat:<15} {_pct(s['passed'], s['total'])}")
    print("\nBy router decision:")
    for route, s in sorted(by_route.items()):
        print(f"  {route:<15} {_pct(s['passed'], s['total'])}   avg ${s['cost_usd'] / s['total']:.4f}")
    if flaky:
        print(f"\nFlaky (mixed results across runs): {', '.join(flaky)}")
    print(f"{'=' * 60}\n")

    def block(s):
        return {"passed": s["passed"], "total": s["total"], "accuracy": round(s["passed"] / s["total"], 4),
                "cost_usd": round(s["cost_usd"], 6)}

    summary = {
        "total": total,
        "passed": passed,
        "accuracy": round(accuracy, 4),
        "avg_time_s": round(avg_time, 2),
        "total_cost_usd": round(total_cost, 6),
        "runs": runs,
        "temperature": temperature,
        "flaky": flaky,
        "by_category": {k: block(v) for k, v in by_category.items()},
        "by_route": {k: block(v) for k, v in by_route.items()},
        "results": results,
    }

    if save_results:
        path = os.path.join(RESULTS_DIR, f"eval_results_{time.strftime('%Y%m%d_%H%M%S')}.json")
        with open(path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"Results saved to: {path}")

    return summary


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case_ids", nargs="*", help="case ids to run (default: all)")
    parser.add_argument("--workers", type=int, default=4, help="parallel cases (default 4)")
    parser.add_argument("--runs", type=int, default=1, help="repeat each case N times")
    parser.add_argument("--temperature", type=float, default=0.0, help="sampling temperature (default 0)")
    parser.add_argument("--no-save", action="store_true", help="do not write eval_results_*.json")
    parser.add_argument("-v", "--verbose", action="store_true")
    a = parser.parse_args()
    run_evals(
        case_ids=a.case_ids or None, verbose=a.verbose, save_results=not a.no_save,
        workers=a.workers, runs=a.runs, temperature=a.temperature,
    )
