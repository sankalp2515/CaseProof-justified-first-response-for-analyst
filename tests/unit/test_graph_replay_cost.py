from contextlib import contextmanager

import pytest

from caseproof.graph.store import GraphStore


def test_replaying_many_old_reports_uses_one_identity_read_and_rejects_changed_ids(
    tmp_path, monkeypatch
):
    store = GraphStore(str(tmp_path / "bank.duckdb"))
    rows = [
        dict(
            update_id="U" + str(i),
            account="A",
            reporting_bank="Bank",
            reported_at="2026-10-16T00:00:00Z",
            balance_minor=100,
            credit_received=[],
            onward_transfers=[],
        )
        for i in range(100)
    ]
    store.apply(rows)
    original = store.bank.connect
    reads = []

    class Connection:
        def __init__(self, db):
            self.db = db

        def execute(self, sql, *args):
            if sql.startswith("SELECT") and "trail_updates" in sql:
                reads.append(sql)
            return self.db.execute(sql, *args)

        def __getattr__(self, name):
            return getattr(self.db, name)

    @contextmanager
    def connect():
        with original() as db:
            yield Connection(db)

    monkeypatch.setattr(store.bank, "connect", connect)
    store.apply(rows)
    assert len(reads) == 1
    with pytest.raises(ValueError, match="changed feed update ID"):
        store.apply([dict(rows[0], balance_minor=200)])
    # Conflicts within a single incoming batch are also rejected atomically.
    new = dict(rows[0], update_id="NEW")
    with pytest.raises(ValueError, match="changed feed update ID"):
        store.apply([new, dict(new, balance_minor=200)])
    with original() as db:
        assert (
            db.execute("SELECT count(*) FROM trail_updates WHERE update_id='NEW'").fetchone()[0]
            == 0
        )
