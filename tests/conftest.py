import duckdb
import pytest

import agent
import db_setup
import tools


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A tiny TPC-H-shaped database; tools/db_setup are pointed at it for the test."""
    path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(path)
    conn.execute("CREATE TABLE nation(n_nationkey BIGINT, n_name VARCHAR)")
    conn.execute("INSERT INTO nation VALUES (0,'ALGERIA'),(1,'ARGENTINA'),(2,'BRAZIL')")
    conn.execute("CREATE TABLE customer(c_custkey BIGINT, c_name VARCHAR, c_nationkey BIGINT, c_acctbal DECIMAL(15,2))")
    conn.execute("INSERT INTO customer VALUES (1,'A',0,10.50),(2,'B',0,20.00),(3,'C',1,-5.25),(4,'D',2,7.00)")
    conn.close()

    monkeypatch.setattr(db_setup, "DB_PATH", path)
    tools.reset_state()
    agent.get_system_blocks.cache_clear()
    yield path
    tools.reset_state()
    agent.get_system_blocks.cache_clear()
