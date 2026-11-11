"""
Heuristic check that the numbers in the model's final answer come from the data.

The answer is free text written by an LLM, so it can misquote a result. We compare
every large number in the answer with the numeric values of the last successful
SQL result. This is a hint, not a proof: derived numbers (sums of rows, ratios)
legitimately won't match, so the UI only shows a soft warning.
"""
import json
import re
from typing import List, Optional

_NUMBER_RE = re.compile(
    r"(?<![\w.])\$?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*(thousand|million|billion|trillion|bn|k|m|b)?\b",
    re.IGNORECASE,
)
_SCALES = {
    "thousand": 1e3, "k": 1e3,
    "million": 1e6, "m": 1e6,
    "billion": 1e9, "bn": 1e9, "b": 1e9,
    "trillion": 1e12,
}
MIN_CHECKED = 1000  # small numbers (ranks, "top 3", percentages) are too often derived


def _answer_numbers(answer: str) -> List[float]:
    out = []
    for m in _NUMBER_RE.finditer(answer):
        value = float((m.group(1) + (m.group(2) or "")).replace(",", ""))
        value *= _SCALES.get((m.group(3) or "").lower(), 1)
        # Skip calendar years such as 1995.
        if m.group(2) is None and not m.group(3) and 1900 <= value <= 2100:
            continue
        if value >= MIN_CHECKED:
            out.append(value)
    return out


def _result_numbers(steps: list) -> Optional[List[float]]:
    """Numeric cell values (plus the row count) of the last successful run_sql step."""
    for step in reversed(steps):
        if step.get("tool") != "run_sql":
            continue
        try:
            data = json.loads(step.get("result", ""))
        except ValueError:
            continue
        if "error" in data:
            continue
        nums = [float(data.get("row_count", 0))]
        for row in data.get("rows", []):
            for v in row.values():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    nums.append(float(v))
        return nums
    return None


def _close(a: float, b: float) -> bool:
    # 1% covers rounding such as "20.5 billion" for 20535072231.
    return abs(a - b) <= 0.01 * max(abs(a), abs(b), 1.0)


def check_answer(answer: str, steps: list) -> dict:
    """
    Returns {"verified": bool | None, "unmatched": [numbers]}.
    verified is None when there was nothing to check (no SQL result or no large numbers).
    """
    nums = _answer_numbers(answer)
    available = _result_numbers(steps)
    if not nums or available is None:
        return {"verified": None, "unmatched": []}
    unmatched = [n for n in nums if not any(_close(n, a) for a in available)]
    return {"verified": not unmatched, "unmatched": unmatched}
