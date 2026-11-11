"""
Compare two eval result files to track improvement across iterations.
Usage: python compare_runs.py eval_results_BEFORE.json eval_results_AFTER.json
"""
import json
import sys
from collections import defaultdict


def _pass_rates(results: list) -> dict:
    """case id -> fraction of runs that passed (handles --runs > 1)."""
    tally = defaultdict(lambda: [0, 0])
    for r in results:
        tally[r["id"]][0] += bool(r["passed"])
        tally[r["id"]][1] += 1
    return {cid: p / n for cid, (p, n) in tally.items()}


def compare(path_a: str, path_b: str) -> None:
    with open(path_a) as f:
        a = json.load(f)
    with open(path_b) as f:
        b = json.load(f)

    print(f"\n{'=' * 65}")
    print(f"{'Metric':<30} {'Before':>10} {'After':>10} {'Delta':>10}")
    print(f"{'=' * 65}")

    print(f"{'Overall accuracy':<30} {a['accuracy']:>9.1%} {b['accuracy']:>9.1%} {b['accuracy'] - a['accuracy']:>+9.1%}")
    print(f"{'Avg time (s)':<30} {a['avg_time_s']:>10.1f} {b['avg_time_s']:>10.1f} {b['avg_time_s'] - a['avg_time_s']:>+10.1f}")
    if "total_cost_usd" in a and "total_cost_usd" in b:
        print(f"{'Total cost ($)':<30} {a['total_cost_usd']:>10.4f} {b['total_cost_usd']:>10.4f} {b['total_cost_usd'] - a['total_cost_usd']:>+10.4f}")

    print(f"\n{'By category':<30}")
    print(f"  {'Category':<20} {'Before':>8} {'After':>8} {'Delta':>8}")
    for cat in sorted(set(a["by_category"]) | set(b["by_category"])):
        acc_a = a["by_category"].get(cat, {}).get("accuracy", 0)
        acc_b = b["by_category"].get(cat, {}).get("accuracy", 0)
        print(f"  {cat:<20} {acc_a:>7.0%} {acc_b:>7.0%} {acc_b - acc_a:>+7.0%}")

    rates_a, rates_b = _pass_rates(a["results"]), _pass_rates(b["results"])
    common = rates_a.keys() & rates_b.keys()
    fixed = sorted(c for c in common if rates_b[c] > rates_a[c])
    broken = sorted(c for c in common if rates_b[c] < rates_a[c])

    if fixed:
        print(f"\nImproved ({len(fixed)}): {', '.join(fixed)}")
    if broken:
        print(f"Regressed ({len(broken)}): {', '.join(broken)}")

    print(f"{'=' * 65}\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python compare_runs.py <before.json> <after.json>")
        sys.exit(1)
    compare(sys.argv[1], sys.argv[2])
