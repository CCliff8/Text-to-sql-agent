"""
Query complexity router.

Classifies a natural language question as 'haiku' (simple) or 'sonnet' (complex)
before any LLM call, so the right model is used from turn 1.

Logic: heuristic signal counting — fast, free, zero dependencies.
A question scoring 2+ complex signals goes to Sonnet; otherwise Haiku.
"""

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
    "at least", "more than",
    # grouping / breakdown
    "per", "by region", "by nation", "by segment", "by ship mode", "breakdown",
]

# Signals that strongly suggest a simple lookup
_SIMPLE_SIGNALS = [
    "how many", "count", "total number", "how much",
    "what is the maximum", "what is the minimum",
    "list all", "show all", "what are the",
]


def classify(question: str) -> str:
    """
    Returns 'haiku' for simple queries, 'sonnet' for complex ones.

    Simple queries:  direct counts, single-table lookups, exact filters
    Complex queries: joins across 3+ tables, rankings, subqueries, percentages
    """
    q = question.lower()

    complex_hits = sum(1 for signal in _COMPLEX_SIGNALS if signal in q)
    simple_hits  = sum(1 for signal in _SIMPLE_SIGNALS  if signal in q)

    # Any complex signal overrides everything → Sonnet
    if complex_hits >= 1:
        return "sonnet"

    # No complex signals, at least one simple signal → Haiku
    if simple_hits >= 1:
        return "haiku"

    # Default: Haiku
    return "haiku"


if __name__ == "__main__":
    tests = [
        ("How many customers are in the database?",               "haiku"),
        ("How many suppliers are there?",                         "haiku"),
        ("How many orders have status F?",                        "haiku"),
        ("What are the top 3 nations by number of customers?",    "sonnet"),
        ("Which segment has the highest total order value?",      "sonnet"),
        ("What percentage of customers have never placed an order?", "sonnet"),
        ("What is the total revenue lost due to discounts in 1995?", "sonnet"),
        ("How many orders were placed in 1994?",                  "haiku"),
        ("What ship mode has the highest average discount?",      "sonnet"),
        ("How many distinct regions are there?",                  "haiku"),
    ]

    print(f"{'Question':<55} {'Expected':<8} {'Got':<8} {'OK'}")
    print("-" * 80)
    correct = 0
    for question, expected in tests:
        got = classify(question)
        ok = "✓" if got == expected else "✗"
        if got == expected:
            correct += 1
        print(f"{question:<55} {expected:<8} {got:<8} {ok}")
    print(f"\n{correct}/{len(tests)} correct")
