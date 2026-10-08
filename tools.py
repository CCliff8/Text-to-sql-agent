"""
SQL tools exposed to the agent via Claude's tool-use API.
"""
import json
import re
from decimal import Decimal
from datetime import date, datetime
from typing import Optional
import duckdb
from db_setup import get_connection


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# ── Schema cache ───────────────────────────────────────────────────────────────

_schema_cache = None  # type: Optional[dict]


def _load_schema(conn: duckdb.DuckDBPyConnection) -> dict:
    global _schema_cache
    if _schema_cache is not None:
        return _schema_cache

    tables = conn.execute("SHOW TABLES").fetchall()
    schema = {}
    for (table_name,) in tables:
        cols = conn.execute(f"DESCRIBE {table_name}").fetchall()
        schema[table_name] = [
            {"column": c[0], "type": c[1]}
            for c in cols
        ]
    _schema_cache = schema
    return schema


# ── SQL safety ─────────────────────────────────────────────────────────────────

# Statements that are never allowed (write, filesystem, network, extensions).
_BLOCKED_KEYWORDS = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|MERGE"
    r"|COPY|EXPORT|IMPORT|ATTACH|DETACH|INSTALL|LOAD|PRAGMA|CALL|SET)\b",
    re.IGNORECASE,
)

# Only these statement types are permitted.
_ALLOWED_STARTS = re.compile(
    r"^\s*(SELECT|WITH|EXPLAIN)\b",
    re.IGNORECASE,
)

# Valid table/column identifier: letters, digits, underscores only.
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_query(query: str) -> Optional[str]:
    """
    Returns an error string if the query is not allowed, else None.
    Strips single-line (--) and block (/* */) comments before checking.
    """
    # Strip comments so they can't be used to hide blocked keywords.
    stripped = re.sub(r"--[^\n]*", " ", query)
    stripped = re.sub(r"/\*.*?\*/", " ", stripped, flags=re.DOTALL).strip()

    if not stripped:
        return "Empty query."

    if _BLOCKED_KEYWORDS.match(stripped):
        return "Only SELECT/WITH/EXPLAIN queries are permitted."

    if not _ALLOWED_STARTS.match(stripped):
        return "Only SELECT/WITH/EXPLAIN queries are permitted."

    return None


def _validate_identifier(name: str) -> Optional[str]:
    """Returns an error string if name is not a safe SQL identifier."""
    if not _SAFE_IDENTIFIER.match(name):
        return f"Invalid identifier: {name!r}. Only letters, digits, and underscores are allowed."
    return None


# ── Tool definitions (passed to Claude) ───────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "get_schema",
        "description": (
            "Returns the database schema: all table names and their columns with data types. "
            "Call this first to understand what tables and columns are available before writing SQL. "
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
            "Only SELECT, WITH (CTEs), and EXPLAIN statements are allowed. "
            "Returns up to 100 rows. On error, returns the error message so you can self-correct."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A SELECT, WITH, or EXPLAIN SQL query. No DDL or DML.",
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

def execute_tool(tool_name: str, tool_input: dict) -> str:
    conn = get_connection()
    try:
        if tool_name == "get_schema":
            schema = _load_schema(conn)
            table_names = tool_input.get("table_names", [])
            if table_names:
                schema = {k: v for k, v in schema.items() if k in table_names}
            return json.dumps(schema, indent=2)

        elif tool_name == "run_sql":
            query = tool_input["query"].strip()

            err = _validate_query(query)
            if err:
                return json.dumps({"error": err})

            try:
                result = conn.execute(query).fetchall()
                cols = [d[0] for d in conn.description]
                rows = [dict(zip(cols, row)) for row in result[:100]]
                return json.dumps({
                    "columns": cols,
                    "rows": rows,
                    "row_count": len(result),
                    "truncated": len(result) > 100,
                }, default=_json_default)
            except Exception as e:
                return json.dumps({"error": str(e)})

        elif tool_name == "sample_table":
            table = tool_input["table_name"]

            err = _validate_identifier(table)
            if err:
                return json.dumps({"error": err})

            limit = min(int(tool_input.get("limit", 5)), 20)
            try:
                result = conn.execute(
                    "SELECT * FROM {} LIMIT {}".format(table, limit)
                ).fetchall()
                cols = [d[0] for d in conn.description]
                rows = [dict(zip(cols, row)) for row in result]
                return json.dumps({"columns": cols, "rows": rows}, default=_json_default)
            except Exception as e:
                return json.dumps({"error": str(e)})

        else:
            return json.dumps({"error": "Unknown tool: {}".format(tool_name)})
    finally:
        conn.close()
