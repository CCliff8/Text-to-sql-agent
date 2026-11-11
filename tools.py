"""
SQL tools exposed to the agent via Claude's tool-use API.

Safety model (defence in depth):
  1. db_setup.get_connection() is read-only, has external access disabled
     (no read_csv / glob / httpfs) and a locked configuration.
  2. Every query must parse as exactly ONE SELECT or EXPLAIN statement.
  3. Queries are interrupted after QUERY_TIMEOUT_S and only MAX_ROWS rows are fetched.
"""
import json
import re
import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import duckdb

import config
from db_setup import get_connection

_ALLOWED_TYPES = {duckdb.StatementType.SELECT, duckdb.StatementType.EXPLAIN}

# DuckDB parses `PRAGMA database_list` etc. as SELECT; they only expose server internals, so refuse them.
_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_INTERNAL_START = re.compile(r"^\s*(PRAGMA|CALL)\b", re.IGNORECASE)


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, (bytes, bytearray)):
        return obj.hex()
    return str(obj)


# ── Shared connection + schema cache ──────────────────────────────────────────

_lock = threading.Lock()
_base_conn = None  # type: Optional[duckdb.DuckDBPyConnection]
_schema_cache = None  # type: Optional[dict]


def _cursor() -> duckdb.DuckDBPyConnection:
    """A fresh cursor on the shared read-only connection (cheap and thread-safe)."""
    global _base_conn
    with _lock:
        if _base_conn is None:
            _base_conn = get_connection()
        return _base_conn.cursor()


def reset_state() -> None:
    """Drop the cached connection and schema (used by tests and after rebuilding the DB)."""
    global _base_conn, _schema_cache
    with _lock:
        if _base_conn is not None:
            _base_conn.close()
        _base_conn = None
        _schema_cache = None


def load_schema() -> dict:
    global _schema_cache
    if _schema_cache is not None:
        return _schema_cache
    cur = _cursor()
    schema = {}
    for (table_name,) in cur.execute("SHOW TABLES").fetchall():
        cols = cur.execute(f'DESCRIBE "{table_name}"').fetchall()
        schema[table_name] = [{"column": c[0], "type": c[1]} for c in cols]
    _schema_cache = schema
    return schema


def get_schema_text() -> str:
    """Compact one-line-per-table schema, suitable for embedding in the system prompt."""
    return "\n".join(
        f"{table}({', '.join(c['column'] + ' ' + c['type'] for c in cols)})"
        for table, cols in load_schema().items()
    )


# ── SQL safety ─────────────────────────────────────────────────────────────────

def _validate_query(cur: duckdb.DuckDBPyConnection, query: str) -> Optional[str]:
    """Returns an error string if the query is not allowed, else None."""
    try:
        statements = cur.extract_statements(query)
    except Exception as e:
        return f"SQL syntax error: {e}"
    if not statements:
        return "Empty query."
    if len(statements) > 1:
        return "Only a single SQL statement is permitted."
    if statements[0].type not in _ALLOWED_TYPES:
        return "Only SELECT/WITH/EXPLAIN queries are permitted."
    if _INTERNAL_START.match(_COMMENTS.sub(" ", query)):
        return "Only SELECT/WITH/EXPLAIN queries are permitted."
    return None


def _validate_identifier(name: str, valid: list) -> Optional[str]:
    """Table names must be one of the real tables (case-insensitive)."""
    if not isinstance(name, str) or name.lower() not in {t.lower() for t in valid}:
        return f"Unknown table: {name!r}. Available tables: {', '.join(sorted(valid))}."
    return None


def run_query(query: str, max_rows: int = config.MAX_ROWS) -> dict:
    """
    Validate and execute a read-only query. Returns either
    {"columns", "rows", "row_count", "truncated"} or {"error"}.
    `row_count` is the number of rows returned; `truncated` means more existed.
    """
    query = (query or "").strip()
    if not query:
        return {"error": "Empty query."}

    cur = _cursor()
    try:
        err = _validate_query(cur, query)
        if err:
            return {"error": err}

        timer = threading.Timer(config.QUERY_TIMEOUT_S, cur.interrupt)
        timer.start()
        try:
            cur.execute(query)
            fetched = cur.fetchmany(max_rows + 1)
            cols = [d[0] for d in cur.description]
        except duckdb.InterruptException:
            return {"error": f"Query exceeded the {config.QUERY_TIMEOUT_S:g}s time limit. Make it cheaper (filter earlier, aggregate, add LIMIT)."}
        finally:
            timer.cancel()

        truncated = len(fetched) > max_rows
        rows = [dict(zip(cols, row)) for row in fetched[:max_rows]]
        return {"columns": cols, "rows": rows, "row_count": len(rows), "truncated": truncated}
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()


# ── Tool definitions (passed to Claude) ───────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "get_schema",
        "description": (
            "Returns the database schema: all table names and their columns with data types. "
            "The schema is already in your instructions, so only call this to re-check specific tables. "
            "Optionally filter to specific tables by passing table_names."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of specific tables to describe. If empty, returns all tables.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "run_sql",
        "description": (
            "Executes a read-only SQL query against the DuckDB database and returns results. "
            f"Exactly one SELECT, WITH (CTE) or EXPLAIN statement is allowed. Returns up to {config.MAX_ROWS} rows "
            "(`truncated` is true if more existed). On error, returns the error message so you can self-correct."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A single SELECT, WITH, or EXPLAIN SQL query. No DDL or DML.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "sample_table",
        "description": (
            "Returns a small sample of rows from a table to understand the data format, "
            "value ranges, and any naming conventions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "The table to sample (must be a valid table name).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of rows to return (default 5, max 20).",
                    "default": 5,
                },
            },
            "required": ["table_name"],
        },
    },
]


# ── Tool execution ─────────────────────────────────────────────────────────────

def result_is_error(result: str) -> bool:
    """True if a tool result string is an {"error": ...} payload."""
    try:
        data = json.loads(result)
    except (TypeError, ValueError):
        return False
    return isinstance(data, dict) and "error" in data


def _dispatch(tool_name: str, tool_input: dict) -> dict:
    if tool_name == "get_schema":
        schema = load_schema()
        wanted = tool_input.get("table_names") or []
        if wanted:
            unknown = [t for t in wanted if t.lower() not in {k.lower() for k in schema}]
            if unknown:
                return {"error": f"Unknown table(s): {unknown}. Available tables: {', '.join(sorted(schema))}."}
            schema = {k: v for k, v in schema.items() if k.lower() in {t.lower() for t in wanted}}
        return schema

    if tool_name == "run_sql":
        return run_query(tool_input.get("query", ""))

    if tool_name == "sample_table":
        table = tool_input.get("table_name")
        err = _validate_identifier(table, list(load_schema()))
        if err:
            return {"error": err}
        try:
            limit = max(1, min(int(tool_input.get("limit", 5)), 20))
        except (TypeError, ValueError):
            return {"error": "limit must be an integer between 1 and 20."}
        result = run_query(f'SELECT * FROM "{table}" LIMIT {limit}', max_rows=limit)
        return result if "error" in result else {"columns": result["columns"], "rows": result["rows"]}

    return {"error": f"Unknown tool: {tool_name}"}


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Run a tool and return a JSON string. Never raises: failures come back as {"error": ...}."""
    try:
        result = _dispatch(tool_name, tool_input or {})
    except Exception as e:  # DB missing, bad input shape, etc. The model can read this.
        result = {"error": f"{type(e).__name__}: {e}"}
    return json.dumps(result, default=_json_default, indent=2 if tool_name == "get_schema" else None)
