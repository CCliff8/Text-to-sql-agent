import json

import pytest

import config
import tools
from db_setup import DatabaseNotReady, get_connection


# ── SQL validation ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "select * from customer",
    "WITH x AS (SELECT 1 AS a) SELECT * FROM x",
    "EXPLAIN SELECT * FROM customer",
    "SELECT 1; ",                      # trailing semicolon is a single statement
    "/* note */ SELECT 1",
    "-- note\nSELECT 1",
])
def test_allowed_queries(db, sql):
    assert "error" not in tools.run_query(sql)


@pytest.mark.parametrize("sql", [
    "DROP TABLE customer",
    "DELETE FROM customer",
    "INSERT INTO customer VALUES (9,'Z',0,1)",
    "CREATE TABLE t AS SELECT 1",
    "ATTACH 'x.db'",
    "COPY customer TO 'out.csv'",
    "SET enable_external_access=true",
    "PRAGMA database_list",
    "/* x */ pragma version",
    "CALL pragma_version()",
    "SELECT 1; DROP TABLE customer",   # stacked statements
    "SELECT 1; SELECT 2",
    "/* SELECT */ DROP TABLE customer",
    "-- SELECT\nDROP TABLE customer",
    "",
    "-- only a comment",
])
def test_blocked_queries(db, sql):
    assert "error" in tools.run_query(sql)
    # and nothing was damaged
    assert tools.run_query("SELECT COUNT(*) AS n FROM customer")["rows"][0]["n"] == 4


@pytest.mark.parametrize("sql", [
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM read_text('/etc/hosts')",
    "SELECT * FROM glob('/*')",
])
def test_filesystem_access_is_blocked(db, sql):
    result = tools.run_query(sql)
    assert "error" in result
    assert "disabled" in result["error"].lower() or "permission" in result["error"].lower()


def test_syntax_error_is_reported(db):
    assert "error" in tools.run_query("SELEC 1")


def test_configuration_is_locked(db):
    conn = get_connection()
    with pytest.raises(Exception):
        conn.execute("SET enable_external_access=true")
    conn.close()


# ── Limits ────────────────────────────────────────────────────────────────────

def test_rows_are_capped_and_flagged(db):
    result = tools.run_query("SELECT * FROM range(1000)")
    assert result["row_count"] == config.MAX_ROWS
    assert result["truncated"] is True
    assert len(result["rows"]) == config.MAX_ROWS


def test_small_result_not_truncated(db):
    result = tools.run_query("SELECT * FROM customer ORDER BY c_custkey")
    assert result["row_count"] == 4 and result["truncated"] is False
    assert result["columns"][0] == "c_custkey"


def test_exactly_max_rows_is_not_truncated(db):
    result = tools.run_query(f"SELECT * FROM range({config.MAX_ROWS})")
    assert result["row_count"] == config.MAX_ROWS and result["truncated"] is False


def test_query_timeout(db, monkeypatch):
    monkeypatch.setattr(config, "QUERY_TIMEOUT_S", 0.3)
    result = tools.run_query("SELECT COUNT(*) FROM range(1000000) a, range(1000000) b")
    assert "time limit" in result["error"]
    # the connection is still usable afterwards
    assert "error" not in tools.run_query("SELECT 1")


# ── execute_tool ──────────────────────────────────────────────────────────────

def test_get_schema_all_and_filtered(db):
    full = json.loads(tools.execute_tool("get_schema", {}))
    assert set(full) == {"nation", "customer"}
    one = json.loads(tools.execute_tool("get_schema", {"table_names": ["customer"]}))
    assert set(one) == {"customer"}
    bad = json.loads(tools.execute_tool("get_schema", {"table_names": ["nope"]}))
    assert "Unknown table" in bad["error"]


def test_schema_text_is_compact(db):
    text = tools.get_schema_text()
    assert "customer(c_custkey BIGINT" in text
    assert text.count("\n") == 1  # one line per table


def test_sample_table(db):
    ok = json.loads(tools.execute_tool("sample_table", {"table_name": "customer", "limit": 2}))
    assert len(ok["rows"]) == 2
    assert "error" in json.loads(tools.execute_tool("sample_table", {"table_name": "customer; DROP TABLE customer"}))
    assert "error" in json.loads(tools.execute_tool("sample_table", {"table_name": "missing"}))
    assert "error" in json.loads(tools.execute_tool("sample_table", {"table_name": "customer", "limit": "abc"}))
    capped = json.loads(tools.execute_tool("sample_table", {"table_name": "customer", "limit": 999}))
    assert len(capped["rows"]) == 4


def test_execute_tool_never_raises(db):
    assert "error" in json.loads(tools.execute_tool("run_sql", {}))              # missing query
    assert "error" in json.loads(tools.execute_tool("run_sql", {"query": None}))
    assert "error" in json.loads(tools.execute_tool("nonexistent", {}))
    assert "error" in json.loads(tools.execute_tool("sample_table", {}))


def test_decimal_and_dates_serialise(db):
    out = json.loads(tools.execute_tool("run_sql", {"query": "SELECT c_acctbal, DATE '1995-01-02' AS d FROM customer LIMIT 1"}))
    assert out["rows"][0] == {"c_acctbal": 10.5, "d": "1995-01-02"}


def test_result_is_error():
    assert tools.result_is_error('{"error": "boom"}')
    assert not tools.result_is_error('{"rows": []}')
    assert not tools.result_is_error("not json")


def test_missing_database_has_friendly_error(tmp_path, monkeypatch):
    import db_setup
    monkeypatch.setattr(db_setup, "DB_PATH", str(tmp_path / "absent.duckdb"))
    tools.reset_state()
    with pytest.raises(DatabaseNotReady, match="db_setup.py"):
        get_connection()
    assert "db_setup.py" in json.loads(tools.execute_tool("run_sql", {"query": "SELECT 1"}))["error"]
    tools.reset_state()
