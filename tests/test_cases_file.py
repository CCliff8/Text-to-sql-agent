"""Sanity checks on test_cases.json itself, so a typo can't silently skew eval results."""
import json
import os
import re

import duckdb
import pytest

import db_setup
from evals import CASES_PATH, _passes

CASES = json.load(open(CASES_PATH))["cases"]
MATCH_TYPES = {"numeric_exact", "numeric_fuzzy", "numeric_any", "contains_string", "contains_any", "contains_all", "regex"}


def test_ids_are_unique_and_fields_present():
    assert len({c["id"] for c in CASES}) == len(CASES)
    for c in CASES:
        assert {"id", "category", "question", "expected_answer", "match_type"} <= set(c)
        assert c["match_type"] in MATCH_TYPES
        assert c.get("gold_sql"), f"{c['id']} has no gold_sql"
        if c["match_type"] == "regex":
            re.compile(c["expected_answer"])
        if c["match_type"] in ("contains_any", "contains_all"):
            assert c.get("options")


@pytest.mark.skipif(not os.path.exists(db_setup.DB_PATH), reason="tpch.duckdb not built (run db_setup.py)")
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_gold_sql_agrees_with_expected_answer(case):
    """The gold query's own output must satisfy the case's answer check."""
    conn = duckdb.connect(db_setup.DB_PATH, read_only=True)
    try:
        golds = case["gold_sql"] if isinstance(case["gold_sql"], list) else [case["gold_sql"]]
        answers = [" ".join(str(cell) for row in conn.execute(sql).fetchall() for cell in row) for sql in golds]
    finally:
        conn.close()
    assert any(_passes(a, case) for a in answers), (case["id"], answers)
