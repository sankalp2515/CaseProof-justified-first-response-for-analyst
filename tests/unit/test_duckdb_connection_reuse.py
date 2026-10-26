import threading

from caseproof.adapters.duckdb_bank import DuckDBBank


def test_nested_use_on_one_thread_reuses_a_single_connection(tmp_path):
    bank = DuckDBBank(tmp_path / "bank.duckdb")
    with bank.connect() as outer:
        with bank.connect() as inner:
            assert inner is outer
            inner.execute("CREATE TABLE t(x INTEGER)")
        # The inner exit must not close the outer connection.
        outer.execute("INSERT INTO t VALUES (1)")
    with bank.connect() as fresh:
        assert fresh is not outer
        assert fresh.execute("SELECT count(*) FROM t").fetchone() == (1,)


def test_other_threads_wait_for_the_held_connection(tmp_path):
    bank = DuckDBBank(tmp_path / "bank.duckdb")
    seen = []

    def other():
        with bank.connect() as connection:
            seen.append(connection)

    with bank.connect() as outer:
        worker = threading.Thread(target=other)
        worker.start()
        worker.join(timeout=0.5)
        # Cross-thread callers do not borrow this thread's connection.
        assert worker.is_alive() and not seen
        held = outer
    worker.join(timeout=10)
    assert seen and seen[0] is not held
