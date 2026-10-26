import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from caseproof.adapters.sqlite_casestore import CaseStore, ConflictError
from caseproof.domain.review import approve
from tests.safety.test_review import ready, reviewer


def test_approval_retry_is_idempotent_and_different_decision_conflicts(tmp_path):
    store, s = ready(tmp_path)
    a = approve(store, s.case_id, reviewer, s.revision, s.digest, "COMPLETE_HANDOFF", "Checked")
    again = approve(store, s.case_id, reviewer, s.revision, s.digest, "COMPLETE_HANDOFF", "Checked")
    assert again.approval_id == a.approval_id
    with pytest.raises(ConflictError, match="immutable"):
        approve(store, s.case_id, reviewer, s.revision, s.digest, "COMPLETE_HANDOFF", "Changed")
    with store.engine.connect() as db:
        rows = db.execute(text("SELECT data FROM approval_history WHERE case_id='C'")).all()
        assert [json.loads(r[0])["approval_id"] for r in rows] == [a.approval_id]
    for table in ("approvals", "approval_history"):
        with pytest.raises(DatabaseError), store.engine.begin() as db:
            db.execute(text(f"DELETE FROM {table} WHERE case_id='C'"))
        with pytest.raises(DatabaseError), store.engine.begin() as db:
            db.execute(text(f"UPDATE {table} SET data='{{}}' WHERE case_id='C'"))
        with pytest.raises(DatabaseError), store.engine.begin() as db:
            db.execute(text(f"INSERT OR REPLACE INTO {table} SELECT * FROM {table}"))
    restarted = CaseStore("sqlite:///" + str(tmp_path / "db.sqlite"))
    assert restarted.get("C").digest == s.digest
    newer = s.model_copy(deep=True)
    newer.revision += 1
    restarted.publish(newer, s.revision)
    approve(
        restarted, "C", reviewer, newer.revision, newer.digest, "COMPLETE_HANDOFF", "New revision"
    )
    with restarted.engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM approval_history")).scalar() == 2


def test_legacy_approval_is_migrated_once_without_changing_payload(tmp_path):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor

    store, s = ready(tmp_path)
    a = approve(store, s.case_id, reviewer, s.revision, s.digest, "COMPLETE_HANDOFF", "Legacy")
    legacy = tmp_path / "legacy.sqlite"
    with sqlite3.connect(legacy) as db:
        db.execute(
            "CREATE TABLE approvals(case_id TEXT,revision INTEGER,data TEXT,"
            "PRIMARY KEY(case_id,revision))"
        )
        db.execute(
            "INSERT INTO approvals VALUES(?,?,?)", (s.case_id, s.revision, a.model_dump_json())
        )
    url = "sqlite:///" + str(legacy)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: CaseStore(url), range(2)))
    with results[0].engine.connect() as db:
        history = db.execute(text("SELECT data FROM approval_history")).all()
        assert len(history) == 1 and history[0][0] == a.model_dump_json()
