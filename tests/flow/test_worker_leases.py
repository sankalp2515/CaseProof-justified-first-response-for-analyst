from sqlalchemy import text

from caseproof.adapters.sqlite_casestore import CaseStore, ConflictError
from caseproof.adapters.sqlite_jobs import SQLiteJobs


def test_expired_worker_is_reclaimed_and_old_owner_cannot_finish(tmp_path):
    store = CaseStore("sqlite:///" + str(tmp_path / "db.sqlite"))
    store.create("A")
    jobs = SQLiteJobs(store)
    job_id = jobs.enqueue("A", 1)
    first = jobs.take()
    with store.engine.begin() as db:
        db.execute(text("UPDATE jobs SET lease_until=0 WHERE job_id=:id"), {"id": job_id})
    recovered = jobs.take()
    assert recovered["job_id"] == job_id and recovered["lease_token"] != first["lease_token"]
    jobs.finish(job_id, "done", lease_token=first["lease_token"])
    assert jobs.get(job_id)["status"] == "running"
    jobs.finish(job_id, "done", lease_token=recovered["lease_token"])
    assert jobs.get(job_id)["status"] == "done"


def test_retry_requires_same_case_revision(tmp_path):
    import pytest

    store = CaseStore("sqlite:///" + str(tmp_path / "db.sqlite"))
    snapshot = store.create("A")
    jobs = SQLiteJobs(store)
    job_id = jobs.enqueue("A", 1)
    job = jobs.take()
    jobs.finish(job_id, "failed", "LOCAL_OCR_ERROR", lease_token=job["lease_token"])
    assert jobs.retry(job_id)["status"] == "queued"
    job = jobs.take()
    jobs.finish(job_id, "failed", "LOCAL_OCR_ERROR", lease_token=job["lease_token"])
    snapshot.revision += 1
    store.publish(snapshot, 1)
    with pytest.raises(ConflictError):
        jobs.retry(job_id)
