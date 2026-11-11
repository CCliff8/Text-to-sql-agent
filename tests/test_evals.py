import pytest

from evals import _extract_numbers, _passes, execution_match, rows_match


def case(**kw):
    base = {"id": "t", "category": "c", "question": "q"}
    base.update(kw)
    return base


def test_extract_numbers():
    assert _extract_numbers("1,234.5 and -7 and 15000") == [1234.5, -7.0, 15000.0]


@pytest.mark.parametrize("c, answer, ok", [
    (case(match_type="numeric_exact", expected_answer="15000"), "There are 15,000 customers.", True),
    (case(match_type="numeric_exact", expected_answer="15000"), "There are 15,001 customers.", False),
    (case(match_type="numeric_fuzzy", expected_answer="1000", tolerance_pct=5), "about 1040", True),
    (case(match_type="numeric_fuzzy", expected_answer="1000", tolerance_pct=5), "about 1100", False),
    (case(match_type="numeric_fuzzy", expected_answer="1000"), "about 1060", False),  # default tolerance is 5%
    (case(match_type="numeric_any", expected_answer="x"), "it is 3", True),
    (case(match_type="numeric_any", expected_answer="x"), "no digits", False),
    (case(match_type="contains_string", expected_answer="AFRICA", case_insensitive=True), "Africa has the most", True),
    (case(match_type="contains_string", expected_answer="AFRICA"), "Africa has the most", False),
    (case(match_type="contains_any", expected_answer="", options=["A", "B"]), "just B", True),
    (case(match_type="contains_all", expected_answer="", options=["IRAQ", "IRAN"], case_insensitive=True), "Iraq and Iran", True),
    (case(match_type="contains_all", expected_answer="", options=["IRAQ", "IRAN"], case_insensitive=True), "Iraq only", False),
    (case(match_type="regex", expected_answer=r"\bO\b"), "status O wins", True),
    (case(match_type="regex", expected_answer=r"\bO\b"), "Orders were many", False),
    (case(match_type="regex", expected_answer=r"(?<!REG )\bAIR\b"), "REG AIR is highest", False),
    (case(match_type="unknown", expected_answer="x"), "x", False),
])
def test_passes(c, answer, ok):
    assert _passes(answer, c) is ok


def test_rows_match_is_order_insensitive_and_tolerant():
    assert rows_match([["A", 1.0], ["B", 2.0]], [["B", 2.001], ["A", 1.0]])
    assert not rows_match([["A", 1.0]], [["A", 1.0], ["B", 2.0]])      # extra row
    assert not rows_match([["A", 1.0]], [["A", 5.0]])                  # wrong value
    assert rows_match([[3]], [["x", 3, "y"]])                          # extra columns allowed
    assert rows_match([["iraq"]], [["IRAQ"]])                          # case-insensitive strings


def _step(rows):
    import json
    return {"tool": "run_sql", "input": {}, "result": json.dumps({"columns": ["a"], "rows": rows})}


def test_execution_match(db):
    c = case(gold_sql="SELECT COUNT(*) FROM customer")
    assert execution_match(c, [_step([{"n": 4}])]) is True
    assert execution_match(c, [_step([{"n": 5}])]) is False
    assert execution_match(c, []) is False
    assert execution_match(case(), [_step([{"n": 4}])]) is None
    # any successful query may match, errors are ignored
    steps = [{"tool": "run_sql", "input": {}, "result": '{"error": "x"}'}, _step([{"n": 9}]), _step([{"n": 4}])]
    assert execution_match(c, steps) is True


def test_execution_match_accepts_any_of_several_gold_queries(db):
    c = case(gold_sql=["SELECT COUNT(*) FROM customer", "SELECT SUM(c_acctbal) FROM customer"])
    assert execution_match(c, [_step([{"v": 32.25}])]) is True
