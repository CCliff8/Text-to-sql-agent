"""
Evaluation framework for the Text-to-SQL agent.

Accuracy modes:
  numeric_exact   — answer must contain this exact number
  numeric_fuzzy   — answer must be within tolerance_pct % of expected
  numeric_any     — answer contains any number (sanity check)
  contains_string — answer contains this string (case-insensitive optional)
  contains_any    — answer contains at least one string from options list
"""
import json
import re
import time
import os
from typing import Any, List, Optional

from agent import run_agent

CASES_PATH = os.path.join(os.path.dirname(__file__), "test_cases.json")
RESULTS_DIR = os.path.dirname(__file__)


# ── Matching helpers ──────────────────────────────────────────────────────────

def _extract_numbers(text: str) -> list[float]:
    """Extract all numbers from text (handles commas in numbers)."""
    cleaned = text.replace(",", "")
    return [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", cleaned)]


def _passes(result_answer: str, case: dict) -> bool:
    answer = result_answer.strip()
    match_type = case["match_type"]
    expected = str(case["expected_answer"])

    if match_type == "numeric_exact":
        numbers = _extract_numbers(answer)
        target = float(expected.replace(",", ""))
        return any(abs(n - target) < 0.5 for n in numbers)

    elif match_type == "numeric_fuzzy":
        numbers = _extract_numbers(answer)
        target = float(expected.replace(",", ""))
        tol = case.get("tolerance_pct", 10) / 100.0
        if target == 0:
            return any(abs(n) < 1 for n in numbers)
        return any(abs(n - target) / abs(target) <= tol for n in numbers)

    elif match_type == "numeric_any":
        return len(_extract_numbers(answer)) > 0

    elif match_type == "contains_string":
        expected_str = expected
        if case.get("case_insensitive", False):
            return expected_str.lower() in answer.lower()
        return expected_str in answer

    elif match_type == "contains_any":
        options = case.get("options", [expected])
        if case.get("case_insensitive", False):
            return any(opt.lower() in answer.lower() for opt in options)
        return any(opt in answer for opt in options)

    return False


# ── Eval runner ───────────────────────────────────────────────────────────────

def run_evals(
    case_ids: Optional[List[str]] = None,
    verbose: bool = False,
    save_results: bool = True,
) -> dict:
    """
    Run the evaluation suite. Returns a summary dict with accuracy metrics.
    """
    with open(CASES_PATH) as f:
        suite = json.load(f)

    cases = suite["cases"]
    if case_ids:
        cases = [c for c in cases if c["id"] in case_ids]

    results = []
    by_category: dict[str, dict] = {}

    print(f"\n{'='*60}")
    print(f"Running {len(cases)} eval cases")
    print(f"{'='*60}\n")

    for i, case in enumerate(cases):
        cid = case["id"]
        question = case["question"]
        category = case["category"]

        print(f"[{i+1:02d}/{len(cases)}] {cid} ({category})")
        print(f"  Q: {question[:80]}{'...' if len(question) > 80 else ''}")

        start = time.time()
        try:
            agent_result = run_agent(question, verbose=verbose)
            elapsed = time.time() - start

            passed = _passes(agent_result["answer"], case)
            status = "PASS" if passed else "FAIL"

            print(f"  {status} ({elapsed:.1f}s, {agent_result['iterations']} iters)")
            if not passed or verbose:
                print(f"  Expected: {case['expected_answer']}")
                print(f"  Got:      {agent_result['answer'][:150]}")

            result = {
                "id": cid,
                "category": category,
                "question": question,
                "expected": case["expected_answer"],
                "answer": agent_result["answer"],
                "sql": agent_result["sql"],
                "passed": passed,
                "elapsed_s": round(elapsed, 2),
                "iterations": agent_result["iterations"],
                "model": agent_result.get("model", ""),
                "routed_to": agent_result.get("routed_to", ""),
                "error": agent_result["error"],
            }

        except Exception as e:
            elapsed = time.time() - start
            print(f"  ERROR: {e}")
            result = {
                "id": cid,
                "category": category,
                "question": question,
                "expected": case["expected_answer"],
                "answer": "",
                "sql": None,
                "passed": False,
                "elapsed_s": round(elapsed, 2),
                "iterations": 0,
                "error": str(e),
            }

        results.append(result)

        # Track by category
        if category not in by_category:
            by_category[category] = {"total": 0, "passed": 0}
        by_category[category]["total"] += 1
        if result["passed"]:
            by_category[category]["passed"] += 1

        print()

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    accuracy = passed / total if total > 0 else 0
    avg_time = sum(r["elapsed_s"] for r in results) / total if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"OVERALL ACCURACY: {passed}/{total} = {accuracy:.1%}")
    print(f"Avg time per question: {avg_time:.1f}s")
    print(f"\nBy category:")
    for cat, stats in sorted(by_category.items()):
        cat_acc = stats["passed"] / stats["total"]
        print(f"  {cat:<15} {stats['passed']}/{stats['total']} = {cat_acc:.0%}")
    print(f"{'='*60}\n")

    summary = {
        "total": total,
        "passed": passed,
        "accuracy": round(accuracy, 4),
        "avg_time_s": round(avg_time, 2),
        "by_category": {
            cat: {
                "passed": stats["passed"],
                "total": stats["total"],
                "accuracy": round(stats["passed"] / stats["total"], 4),
            }
            for cat, stats in by_category.items()
        },
        "results": results,
    }

    if save_results:
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(RESULTS_DIR, f"eval_results_{ts}.json")
        with open(path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"Results saved to: {path}")

    return summary


if __name__ == "__main__":
    import sys
    case_ids = sys.argv[1:] if len(sys.argv) > 1 else None
    run_evals(case_ids=case_ids, verbose=False)
