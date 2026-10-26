import threading
import time
import uuid
from contextlib import contextmanager

from sqlalchemy import text


class SQLiteJobs:
    def __init__(self, store):
        self.store = store
        self.lease_seconds = 90
        with store.engine.begin() as db:
            db.exec_driver_sql("BEGIN IMMEDIATE")
            columns = {r[1] for r in db.execute(text("PRAGMA table_info(jobs)"))}
            if "priority" not in columns:
                db.execute(text("ALTER TABLE jobs ADD COLUMN priority INTEGER NOT NULL DEFAULT 0"))
            if "lease_until" not in columns:
                db.execute(text("ALTER TABLE jobs ADD COLUMN lease_until REAL DEFAULT 0"))
            if "lease_token" not in columns:
                db.execute(text("ALTER TABLE jobs ADD COLUMN lease_token TEXT"))
            for name, declaration in {
                "enqueued_at": "REAL",
                "started_at": "REAL",
                "finished_at": "REAL",
                "attempt_count": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if name not in columns:
                    db.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {declaration}"))
            # Cover every atomic intent producer, including direct INSERTs in
            # case publication/bank wakeups. Historical times remain unknown.
            db.execute(
                text(
                    "CREATE TRIGGER IF NOT EXISTS jobs_enqueue_timestamp AFTER INSERT ON jobs "
                    "WHEN NEW.enqueued_at IS NULL BEGIN UPDATE jobs "
                    "SET enqueued_at=(julianday('now')-2440587.5)*86400.0 "
                    "WHERE job_id=NEW.job_id; END"
                )
            )

    def enqueue(self, case_id, revision, priority=0):
        if not 0 <= priority <= 10:
            raise ValueError("invalid job priority")
        job_id = "JOB-" + uuid.uuid4().hex[:12]
        with self.store.engine.begin() as db:
            # A newer revision supersedes earlier jobs that no completed job has covered
            # (queued, running, failed or stale). Inherit their priority so background
            # refreshes cannot demote an interactive complaint behind the backlog.
            inherited = db.execute(
                text(
                    "SELECT max(priority) FROM jobs WHERE case_id=:c AND revision<:r "
                    "AND revision>coalesce((SELECT max(revision) FROM jobs "
                    "WHERE case_id=:c AND status='done'),-1)"
                ),
                {"c": case_id, "r": revision},
            ).scalar()
            priority = max(priority, inherited or 0)
            db.execute(
                text(
                    "INSERT OR IGNORE INTO jobs(job_id,case_id,revision,status,error,priority) "
                    "VALUES(:id,:case,:r,'queued',NULL,:priority)"
                ),
                dict(id=job_id, case=case_id, r=revision, priority=priority),
            )
            db.execute(
                text(
                    "UPDATE jobs SET priority=max(priority,:p) "
                    "WHERE case_id=:c AND revision=:r AND status='queued'"
                ),
                {"p": priority, "c": case_id, "r": revision},
            )
            row = db.execute(
                text("SELECT job_id FROM jobs WHERE case_id=:case AND revision=:r"),
                dict(case=case_id, r=revision),
            ).first()
        return row[0]

    def get(self, job_id):
        with self.store.engine.connect() as db:
            r = db.execute(text("SELECT * FROM jobs WHERE job_id=:id"), dict(id=job_id)).first()
        if not r:
            raise KeyError("job not found")
        return dict(r._mapping)

    def take(self):
        with self.store.engine.begin() as db:
            db.execute(
                text(
                    "UPDATE jobs SET status='stale' WHERE status='queued' AND EXISTS "
                    "(SELECT 1 FROM cases c WHERE c.case_id=jobs.case_id "
                    "AND c.revision!=jobs.revision)"
                )
            )
            db.execute(
                text(
                    "UPDATE jobs SET status='queued',lease_token=NULL "
                    "WHERE status='running' AND lease_until<:now"
                ),
                {"now": time.time()},
            )
            r = db.execute(
                text(
                    "UPDATE jobs SET status='running',lease_token=:token,lease_until=:until, "
                    "started_at=:started,finished_at=NULL,attempt_count=attempt_count+1 "
                    "WHERE job_id=(SELECT job_id FROM jobs WHERE status='queued' "
                    "ORDER BY priority DESC,rowid LIMIT 1) AND status='queued' RETURNING *"
                ),
                {
                    "token": uuid.uuid4().hex,
                    "until": time.time() + self.lease_seconds,
                    "started": time.time(),
                },
            ).first()
            return dict(r._mapping) if r else None

    def finish(self, job_id, status, error=None, lease_token=None):
        with self.store.engine.begin() as db:
            db.execute(
                text(
                    "UPDATE jobs SET status=:s,error=:e,lease_until=0,finished_at=:at "
                    "WHERE job_id=:id "
                    "AND (:token IS NULL OR lease_token=:token)"
                ),
                dict(s=status, e=error, id=job_id, token=lease_token, at=time.time()),
            )

    def retry(self, job_id):
        job = self.get(job_id)
        if job["status"] != "failed" or self.store.get(job["case_id"]).revision != job["revision"]:
            from caseproof.adapters.sqlite_casestore import ConflictError

            raise ConflictError("job_no_longer_retryable")
        with self.store.engine.begin() as db:
            db.execute(
                text(
                    "UPDATE jobs SET status='queued',error=NULL,priority=10 WHERE job_id=:id "
                    "AND status='failed'"
                ),
                {"id": job_id},
            )
        return self.get(job_id)

    @contextmanager
    def lease(self, job):
        stopped = threading.Event()

        def heartbeat():
            while not stopped.wait(max(0.05, self.lease_seconds / 3)):
                with self.store.engine.begin() as db:
                    db.execute(
                        text(
                            "UPDATE jobs SET lease_until=:until WHERE job_id=:id "
                            "AND status='running' AND lease_token=:token"
                        ),
                        {
                            "until": time.time() + self.lease_seconds,
                            "id": job["job_id"],
                            "token": job["lease_token"],
                        },
                    )

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            thread.join(timeout=5)
