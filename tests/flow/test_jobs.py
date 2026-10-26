from caseproof.config import Settings
from caseproof.pipeline.orchestrator import Orchestrator
from caseproof.worker import run_one


def runtime(tmp_path):
    return Orchestrator(
        Settings(
            _env_file=None,
            llm_mode="mock",
            data_dir=tmp_path,
            object_dir=tmp_path / "objects",
            sqlite_url="sqlite:///" + str(tmp_path / "db.sqlite"),
            duckdb_path=str(tmp_path / "bank.duckdb"),
        )
    )


def test_duplicate_job_publishes_once(tmp_path):
    o = runtime(tmp_path)
    s = o.store.create("J", customer_account="test")
    o.intake.add("J", b"I paid INR 100 on 2026-10-01 11:29", "text/plain", "narrative")
    s = o.store.get("J")
    a = o.jobs.enqueue("J", s.revision)
    b = o.jobs.enqueue("J", s.revision)
    assert a == b
    run_one(o.jobs, o)
    assert o.jobs.get(a)["status"] == "done"
    revision = o.store.get("J").revision
    assert run_one(o.jobs, o) is None
    assert o.store.get("J").revision == revision


def test_stale_job_does_not_overwrite(tmp_path):
    o = runtime(tmp_path)
    s = o.store.create("J", customer_account="test")
    job = o.jobs.enqueue("J", s.revision)
    o.intake.add("J", b"hi", "text/plain", "narrative")
    revision = o.store.get("J").revision
    run_one(o.jobs, o)
    assert o.jobs.get(job)["status"] == "stale"
    # Intake now atomically queues its current revision. The stale job is skipped
    # and the legitimate latest intent runs; old evidence cannot overwrite it.
    assert o.store.get("J").revision == revision + 1
    assert o.store.get("J", revision).artifacts == o.store.get("J").artifacts


def test_interactive_work_is_not_blocked_by_background_refresh_backlog(tmp_path):
    from tests.flow.test_api import client

    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        for cid in ("BACKGROUND", "USER"):
            o.store.create(cid)
        background = o.jobs.enqueue("BACKGROUND", 1)
        interactive = o.jobs.enqueue("USER", 1, priority=10)
        assert o.jobs.take()["job_id"] == interactive
        assert o.jobs.take()["job_id"] == background


def test_bank_refresh_carries_interactive_priority_to_new_revision(tmp_path):
    o = runtime(tmp_path)
    o.store.create("ACTIVE")
    o.store.create("OLD")
    o.jobs.enqueue("OLD", 1, priority=5)
    s = o.intake.add("ACTIVE", b"new evidence", "text/plain", "narrative")
    prior = s.revision
    s.revision += 1
    o.store.publish(s, prior, "bank_imported:fresh-coverage")
    job = o.jobs.take()
    assert job["case_id"] == "ACTIVE" and job["revision"] == s.revision
    assert job["priority"] == 10


def test_superseding_job_keeps_unfinished_interactive_priority(tmp_path):
    from sqlalchemy import text

    o = runtime(tmp_path)
    o.store.create("J", customer_account="test")
    o.store.create("B", customer_account="other")
    interactive = o.jobs.enqueue("J", 1, priority=10)
    with o.store.engine.begin() as db:  # e.g. OCR was unavailable
        db.execute(text("UPDATE jobs SET status='failed' WHERE job_id=:j"), {"j": interactive})
    # A background refresh publishes a newer revision without a priority of its own.
    superseding = o.jobs.enqueue("J", 2)
    assert o.jobs.get(superseding)["priority"] == 10
    # Once a job has completed the case, later background work stays background.
    with o.store.engine.begin() as db:
        db.execute(text("UPDATE jobs SET status='done' WHERE job_id=:j"), {"j": superseding})
    assert o.jobs.get(o.jobs.enqueue("J", 3))["priority"] == 0
    # Other cases are unaffected.
    assert o.jobs.get(o.jobs.enqueue("B", 1))["priority"] == 0
