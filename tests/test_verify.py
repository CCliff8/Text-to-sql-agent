import json

from verify import check_answer


def _steps(rows, truncated=False):
    return [{"tool": "run_sql", "input": {}, "result": json.dumps({"columns": list(rows[0]), "rows": rows, "row_count": len(rows), "truncated": truncated})}]


def test_matching_number_verifies():
    steps = _steps([{"n": 15000}])
    assert check_answer("There are 15,000 customers.", steps) == {"verified": True, "unmatched": []}


def test_misquoted_number_is_flagged():
    steps = _steps([{"n": 15000}])
    out = check_answer("There are 51,000 customers.", steps)
    assert out["verified"] is False and out["unmatched"] == [51000.0]


def test_scale_words_and_rounding():
    steps = _steps([{"revenue": 20535072231.4}])
    assert check_answer("Revenue was about 20.5 billion dollars.", steps)["verified"] is True
    assert check_answer("Revenue was $20,535,072,231.40.", steps)["verified"] is True


def test_years_and_small_numbers_are_ignored():
    steps = _steps([{"n": 7}])
    assert check_answer("The top 3 nations in 1995 had 7 each.", steps) == {"verified": None, "unmatched": []}


def test_row_count_counts_as_a_match():
    steps = _steps([{"x": i} for i in range(5)])
    assert check_answer("5 rows", steps)["verified"] is None  # small number, ignored


def test_nothing_to_check():
    assert check_answer("There are 15,000 customers.", [])["verified"] is None
    err = [{"tool": "run_sql", "input": {}, "result": json.dumps({"error": "boom"})}]
    assert check_answer("There are 15,000 customers.", err)["verified"] is None


def test_uses_last_successful_query():
    steps = _steps([{"n": 111111}]) + _steps([{"n": 222222}]) + [{"tool": "run_sql", "input": {}, "result": '{"error": "x"}'}]
    assert check_answer("It is 222,222.", steps)["verified"] is True
