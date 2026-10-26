"""Case-scoped transactional jobs with fencing; Tasks is delivery, not truth."""

import threading
import time
import uuid
from contextlib import contextmanager

from caseproof.adapters.sqlite_casestore import ConflictError


class FirestoreJobs:
    def __init__(self, store, lease_seconds=90):
        self.store, self.documents, self.lease_seconds = store, store.documents, lease_seconds

    def enqueue(self, case_id, revision, priority=0):
        if not 0 <= priority <= 10:
            raise ValueError("invalid job priority")

        def commit(tx):
            case = tx.get(self.store.case_path(case_id))
            if not case or case["revision"] != revision:
                raise ConflictError("stale_revision")
            return self.store.job_write(tx, case, revision, priority)

        return self.documents.transact(commit)

    def get(self, jid):
        row = self.documents.get("jobs/" + jid)
        if row is None:
            raise KeyError("job not found")
        return row

    def claim(self, jid):
        def commit(tx):
            job = tx.get("jobs/" + jid)
            if not job:
                raise KeyError("job not found")
            case = tx.get(self.store.case_path(job["case_id"]))
            if job["status"] in {"done", "stale", "failed"}:
                return None
            if case["revision"] != job["revision"]:
                job.update(status="stale", finished_at=time.time())
                tx.set("jobs/" + jid, job)
                return None
            if job["status"] == "running" and job["lease_until"] > time.time():
                raise ConflictError("job_already_running")
            job.update(
                status="running",
                lease_token=uuid.uuid4().hex,
                lease_until=time.time() + self.lease_seconds,
                started_at=time.time(),
                finished_at=None,
                attempt_count=job["attempt_count"] + 1,
            )
            tx.set("jobs/" + jid, job)
            return job

        return self.documents.transact(commit)

    def take(self):
        rows = self.documents.query("jobs", [("status", "queued")], limit=100)
        for row in sorted(rows, key=lambda r: (-r["priority"], r["enqueued_at"])):
            claimed = self.claim(row["job_id"])
            if claimed:
                return claimed
        return None

    def finish(self, jid, status, error=None, lease_token=None):
        if status not in {"done", "failed", "stale"} or not lease_token:
            raise ValueError("Fenced job completion required")

        def commit(tx):
            job = tx.get("jobs/" + jid)
            if not job or job["lease_token"] != lease_token or job["status"] != "running":
                raise ConflictError("job_lease_lost")
            job.update(status=status, error=error, lease_until=0, finished_at=time.time())
            tx.set("jobs/" + jid, job)

        self.documents.transact(commit)

    def retry(self, jid):
        def commit(tx):
            job = tx.get("jobs/" + jid)
            case = tx.get(self.store.case_path(job["case_id"])) if job else None
            if not job or job["status"] != "failed" or case["revision"] != job["revision"]:
                raise ConflictError("job_no_longer_retryable")
            intent = tx.get("task_intents/" + jid)
            job.update(status="queued", error=None, priority=10)
            intent.update(state="pending", generation=intent["generation"] + 1)
            tx.set("jobs/" + jid, job)
            tx.set("task_intents/" + jid, intent)
            return job

        return self.documents.transact(commit)

    def defer(self, job, error):
        def commit(tx):
            latest = tx.get("jobs/" + job["job_id"])
            if latest["status"] != "running" or latest["lease_token"] != job["lease_token"]:
                raise ConflictError("job_lease_lost")
            latest.update(status="queued", lease_until=0, lease_token=None, error=error)
            tx.set("jobs/" + job["job_id"], latest)

        self.documents.transact(commit)

    @contextmanager
    def lease(self, job):
        stopped = threading.Event()

        def renew():
            while not stopped.wait(max(0.1, self.lease_seconds / 3)):

                def commit(tx):
                    latest = tx.get("jobs/" + job["job_id"])
                    if latest["status"] != "running" or latest["lease_token"] != job["lease_token"]:
                        raise ConflictError("job_lease_lost")
                    latest["lease_until"] = time.time() + self.lease_seconds
                    tx.set("jobs/" + job["job_id"], latest)

                try:
                    self.documents.transact(commit)
                except Exception:
                    stopped.set()  # completion also fences; failed renewal cannot grant a new lease

        thread = threading.Thread(target=renew, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            thread.join(timeout=25)
