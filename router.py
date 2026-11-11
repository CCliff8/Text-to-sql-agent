"""
Query complexity router.

Classifies a natural language question as 'haiku' (simple) or 'sonnet' (complex)
before any LLM call, so the right model is used from turn 1.

Logic: whole-word signal matching, free and dependency-free. A single complex
signal sends the question to Sonnet; everything else goes to Haiku, which the
agent escalates to Sonnet automatically if it struggles.
"""
import re

# Signals that suggest a query needs multi-step reasoning or complex SQL
_COMPLEX_SIGNALS = [
    # ranking / ordering
    "top", "bottom", "rank", "highest", "lowest", "most", "least",
    "best", "worst", "first", "last",
    # aggregation / math
    "average", "percent", "percentage", "ratio", "rate", "total revenue",
    "revenue lost", "profit", "sum of",
    # multi-entity comparison
    "compare", "versus", "vs", "difference between", "more than", "less than",
    "above average", "below average",
    # time complexity
    "per year", "per month", "over time", "trend", "quarter", "q1", "q2", "q3", "q4",
    # subquery patterns
    "who has", "which customer", "which supplier", "have never", "have not",
    "at least",
    # grouping / breakdown
    "per", "by region", "by nation", "by segment", "by ship mode", "breakdown",
]

# \b so that "per" does not match "operation" and "rate" does not match "generate".
_COMPLEX_RE = re.compile(r"\b(?:" + "|".join(re.escape(s) for s in _COMPLEX_SIGNALS) + r")\b")


def classify(question: str) -> str:
    """Returns 'sonnet' if the question has any complex signal, else 'haiku'."""
    return "sonnet" if _COMPLEX_RE.search(question.lower()) else "haiku"
