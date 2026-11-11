"""
Set up DuckDB with TPC-H data at scale factor 0.1 (~100MB).
TPC-H is a standard business benchmark with realistic tables:
  customer, orders, lineitem, part, supplier, partsupp, nation, region
"""
import os

import duckdb

import config

DB_PATH = os.path.join(os.path.dirname(__file__), "tpch.duckdb")

TPCH_TABLES = ("customer", "orders", "lineitem", "part", "supplier", "partsupp", "nation", "region")


class DatabaseNotReady(RuntimeError):
    """Raised when the TPC-H database file has not been built yet."""


def setup_database(scale_factor: float = 0.1) -> None:
    conn = duckdb.connect(DB_PATH)
    try:
        existing = {t[0] for t in conn.execute("SHOW TABLES").fetchall()}

        if set(TPCH_TABLES).issubset(existing):
            row_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            if row_count > 0:
                print(f"Database already loaded ({row_count:,} orders). Skipping setup.")
                return

        print(f"Loading TPC-H data at scale factor {scale_factor}...")
        conn.execute("INSTALL tpch")
        conn.execute("LOAD tpch")
        conn.execute(f"CALL dbgen(sf={float(scale_factor)})")

        for table in TPCH_TABLES:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {count:,} rows")

        print("Done.")
    finally:
        conn.close()


def get_connection() -> duckdb.DuckDBPyConnection:
    """
    Read-only connection with filesystem/network access disabled, resource limits
    applied and the configuration locked, so SQL cannot read local files
    (read_csv, glob, ...) or loosen its own sandbox.
    """
    if not os.path.exists(DB_PATH):
        raise DatabaseNotReady(
            f"Database not found at {DB_PATH}. Build it first with: python db_setup.py"
        )
    conn = duckdb.connect(
        DB_PATH,
        read_only=True,
        config={
            "enable_external_access": False,
            "memory_limit": config.DUCKDB_MEMORY_LIMIT,
            "threads": config.DUCKDB_THREADS,
        },
    )
    conn.execute("SET lock_configuration=true")
    return conn


if __name__ == "__main__":
    setup_database()
