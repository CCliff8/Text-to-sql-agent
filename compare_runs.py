"""
Compare two eval result files to track improvement across iterations.
Usage: python compare_runs.py eval_results_BEFORE.json eval_results_AFTER.json
"""
import json
import sys


def compare(path_a: str, path_b: str):
    with open(path_a) as f:
        a = json.load(f)
    with open(path_b) as f:
        b = json.load(f)

    print(f"\n{'='*65}")
    print(f"{'Metric':<30} {'Before':>10} {'After':>10} {'Delta':>10}")
    print(f"{'='*65}")

    acc_a = a["accuracy"]
    acc_b = b["accuracy"]
    print(f"{'Overall accuracy':<30} {acc_a:>9.1%} {acc_b:>9.1%} {acc_b-acc_a:>+9.1%}")
    print(f"{'Avg time (s)':<30} {a['avg_time_s']:>10.1f} {b['avg_time_s']:>10.1f} {b['avg_time_s']-a['avg_time_s']:>+10.1f}")

    print(f"\n{'By category':<30}")
    print(f"  {'Category':<20} {'Before':>8} {'After':>8} {'Delta':>8}")
    cats = sorted(set(a["by_category"]) | set(b["by_category"]))
    for cat in cats:
        acc_a_cat = a["by_category"].get(cat, {}).get("accuracy", 0)
        acc_b_cat = b["by_category"].get(cat, {}).get("accuracy", 0)
        print(f"  {cat:<20} {acc_a_cat:>7.0%} {acc_b_cat:>7.0%} {acc_b_cat-acc_a_cat:>+7.0%}")

    # Which cases flipped?
    results_a = {r["id"]: r for r in a["results"]}
    results_b = {r["id"]: r for r in b["results"]}
    fixed = [id for id in results_a if not results_a[id]["passed"] and results_b.get(id, {}).get("passed")]
    broken = [id for id in results_a if results_a[id]["passed"] and not results_b.get(id, {}).get("passed")]

    if fixed:
        print(f"\nFixed ({len(fixed)}): {', '.join(fixed)}")
    if broken:
        print(f"Broken ({len(broken)}): {', '.join(broken)}")

    print(f"{'='*65}\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python compare_runs.py <before.json> <after.json>")
        sys.exit(1)
    compare(sys.argv[1], sys.argv[2])
