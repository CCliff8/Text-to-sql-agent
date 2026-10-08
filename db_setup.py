"""
Set up DuckDB with TPC-H data at scale factor 0.1 (~100MB).
TPC-H is a standard business benchmark with realistic tables:
  customer, orders, lineitem, part, supplier, partsupp, nation, region
"""
import duckdb
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "tpch.duckdb")


def setup_database(scale_factor: float = 0.1) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(DB_PATH)

    # Check if already populated
    tables = conn.execute("SHOW TABLES").fetchall()
    tpch_tables = {"customer", "orders", "lineitem", "part", "supplier", "partsupp", "nation", "region"}
    existing = {t[0] for t in tables}

    if tpch_tables.issubset(existing):
        row_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        if row_count > 0:
            print(f"Database already loaded ({row_count:,} orders). Skipping setup.")
            return conn

    print(f"Loading TPC-H data at scale factor {scale_factor}...")
    conn.execute("INSTALL tpch")
    conn.execute("LOAD tpch")
    conn.execute(f"CALL dbgen(sf={scale_factor})")

    for table in tpch_tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count:,} rows")

    print("Done.")
    return conn


def get_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DB_PATH, read_only=True)


if __name__ == "__main__":
    setup_database()
