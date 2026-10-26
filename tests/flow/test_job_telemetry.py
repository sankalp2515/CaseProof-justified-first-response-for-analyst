from sqlalchemy import text

from tests.flow.test_jobs import runtime


def test_atomic_intake_job_has_persisted_enqueue_and_attempt_times(tmp_path):
    o = runtime(tmp_path)
    o.store.create("METRICS")
    snap = o.intake.add("METRICS", b"new complaint", "text/plain", "narrative")
    job = o.jobs.enqueue("METRICS", snap.revision)
    queued = o.jobs.get(job)
    assert queued["enqueued_at"] > 0
    assert queued["attempt_count"] == 0 and queued["started_at"] is None
    running = o.jobs.take()
    assert running["attempt_count"] == 1
    assert running["started_at"] >= queued["enqueued_at"] - 0.01
    o.jobs.finish(job, "failed", "LOCAL_OCR_ERROR", running["lease_token"])
    failed = o.jobs.get(job)
    assert failed["finished_at"] >= running["started_at"]
    o.jobs.retry(job)
    retried = o.jobs.take()
    assert retried["attempt_count"] == 2
    assert retried["enqueued_at"] == queued["enqueued_at"]
    assert retried["finished_at"] is None


def test_expired_lease_reclaim_is_counted_and_fenced_finish_cannot_change_metrics(tmp_path):
    o = runtime(tmp_path)
    o.store.create("LEASE")
    jid = o.jobs.enqueue("LEASE", 1)
    first = o.jobs.take()
    with o.store.engine.begin() as db:
        db.execute(text("UPDATE jobs SET lease_until=0 WHERE job_id=:j"), {"j": jid})
    second = o.jobs.take()
    assert second["attempt_count"] == 2
    o.jobs.finish(jid, "done", lease_token=first["lease_token"])
    current = o.jobs.get(jid)
    assert current["status"] == "running" and current["finished_at"] is None


def test_historical_enqueue_time_is_unknown_rather_than_fabricated(tmp_path):
    from caseproof.adapters.sqlite_casestore import CaseStore
    from caseproof.adapters.sqlite_jobs import SQLiteJobs

    store = CaseStore("sqlite:///" + str(tmp_path / "legacy.db"))
    store.create("OLD")
    with store.engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO jobs(job_id,case_id,revision,status,error) "
                "VALUES('OLD-JOB','OLD',1,'done',NULL)"
            )
        )
    jobs = SQLiteJobs(store)
    assert jobs.get("OLD-JOB")["enqueued_at"] is None
