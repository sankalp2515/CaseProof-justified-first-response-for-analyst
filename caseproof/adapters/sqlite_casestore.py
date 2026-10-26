import json
import uuid
from contextlib import nullcontext
from pathlib import Path

from sqlalchemy import create_engine, text

from caseproof.domain.contracts import CaseSnapshot, now

OPERATIONAL_METADATA = {
    "customer_account",
    "reported_at",
    "first_contact",
    "kit_case_id",
    "contact_time_unknown",
    "channel",
    "selected_transaction_ids",
    "submission_digest",
    "payment_authorisation",
    "complaint_references",
}


class ConflictError(ValueError):
    pass


class CaseStore:
    def __init__(self, url):
        path = url.removeprefix("sqlite:///")
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
        with self.engine.begin() as db:
            # API and worker can start together. Serialize schema/history migration before
            # either process reads the legacy approval rows and installs immutable triggers.
            db.exec_driver_sql("BEGIN IMMEDIATE")
            for sql in [
                (
                    "CREATE TABLE IF NOT EXISTS cases(case_id TEXT PRIMARY KEY,"
                    " tenant_id TEXT, metadata TEXT, revision INTEGER)"
                ),
                (
                    "CREATE TABLE IF NOT EXISTS snapshots(case_id TEXT,revision"
                    " INTEGER,digest TEXT,data TEXT,PRIMARY KEY(case_id,revisio"
                    "n))"
                ),
                (
                    "CREATE TABLE IF NOT EXISTS audit_events(id INTEGER PRIMARY"
                    " KEY,case_id TEXT,revision INTEGER,event TEXT,at TEXT)"
                ),
                (
                    "CREATE TABLE IF NOT EXISTS approvals(case_id TEXT,revision"
                    " INTEGER,data TEXT,PRIMARY KEY(case_id,revision))"
                ),
                (
                    "CREATE TABLE IF NOT EXISTS outbox(key TEXT PRIMARY KEY,cas"
                    "e_id TEXT,revision INTEGER,kind TEXT,payload TEXT,status T"
                    "EXT,response TEXT)"
                ),
                (
                    "CREATE TABLE IF NOT EXISTS jobs(job_id TEXT PRIMARY KEY,ca"
                    "se_id TEXT,revision INTEGER,status TEXT,error TEXT,UNIQUE("
                    "case_id,revision))"
                ),
            ]:
                db.execute(text(sql))
            columns = {r[1] for r in db.execute(text("PRAGMA table_info(jobs)"))}
            if "priority" not in columns:
                db.execute(text("ALTER TABLE jobs ADD COLUMN priority INTEGER NOT NULL DEFAULT 0"))
            db.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS approval_history(approval_id TEXT PRIMARY KEY,"
                    "case_id TEXT,revision INTEGER,data TEXT,UNIQUE(case_id,revision))"
                )
            )
            # Preserve all surviving legacy decisions; prior overwritten data cannot be recovered.
            for row in db.execute(text("SELECT case_id,revision,data FROM approvals")).all():
                if not db.execute(
                    text("SELECT 1 FROM approval_history WHERE case_id=:cid AND revision=:r"),
                    dict(cid=row[0], r=row[1]),
                ).first():
                    db.execute(
                        text("INSERT INTO approval_history VALUES(:aid,:cid,:r,:data)"),
                        dict(
                            aid=json.loads(row[2])["approval_id"], cid=row[0], r=row[1], data=row[2]
                        ),
                    )
            for table in ("approvals", "approval_history", "snapshots"):
                for operation in ("UPDATE", "DELETE"):
                    db.execute(
                        text(
                            f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()} "
                            f"BEFORE {operation} ON {table} BEGIN "
                            "SELECT RAISE(ABORT,'immutable approval'); END"
                        )
                    )
                extra = " OR approval_id=NEW.approval_id" if table == "approval_history" else ""
                db.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_insert "
                        f"BEFORE INSERT ON {table} "
                        f"WHEN EXISTS(SELECT 1 FROM {table} WHERE "
                        f"(case_id=NEW.case_id AND revision=NEW.revision){extra}) "
                        "BEGIN SELECT RAISE(ABORT,'immutable approval'); END"
                    )
                )
            # Remove retired benchmark labels from legacy metadata, preserving evidence revisions.
            allowed = OPERATIONAL_METADATA
            for row in db.execute(text("SELECT case_id,metadata,revision FROM cases")).all():
                old = json.loads(row[1])
                clean = {k: v for k, v in old.items() if k in allowed}
                if old != clean:
                    db.execute(
                        text("UPDATE cases SET metadata=:meta WHERE case_id=:id"),
                        dict(id=row[0], meta=json.dumps(clean)),
                    )
                    db.execute(
                        text(
                            (
                                "INSERT INTO audit_events(case_id,revision,event,at) VALUES"
                                "(:id,:r,'metadata_label_migration',:at)"
                            )
                        ),
                        dict(id=row[0], r=row[2], at=now()),
                    )

    def create(self, case_id=None, tenant_id="demo", **meta):
        if set(meta) - {
            "customer_account",
            "reported_at",
            "first_contact",
            "kit_case_id",
            "contact_time_unknown",
            "channel",
            "selected_transaction_ids",
            "submission_digest",
            "payment_authorisation",
            "complaint_references",
        }:
            raise ValueError("non-operational metadata forbidden")
        case_id = case_id or "CASE-" + uuid.uuid4().hex[:10]
        snap = CaseSnapshot(case_id=case_id, revision=1).seal()
        with self.engine.begin() as db:
            db.execute(
                text("INSERT INTO cases VALUES(:id,:tenant,:meta,1)"),
                dict(id=case_id, tenant=tenant_id, meta=json.dumps(meta)),
            )
            db.execute(
                text("INSERT INTO snapshots VALUES(:id,1,:digest,:data)"),
                dict(id=case_id, digest=snap.digest, data=snap.model_dump_json()),
            )
        return snap

    def metadata(self, case_id):
        with self.engine.connect() as db:
            r = db.execute(
                text("SELECT tenant_id,metadata,revision FROM cases WHERE case_id=:id"),
                dict(id=case_id),
            ).first()
        if not r:
            raise KeyError("case not found")
        return {
            **{
                k: v
                for k, v in json.loads(r[1]).items()
                if k
                in {
                    "customer_account",
                    "reported_at",
                    "first_contact",
                    "kit_case_id",
                    "contact_time_unknown",
                    "channel",
                    "selected_transaction_ids",
                    "submission_digest",
                    "payment_authorisation",
                    "complaint_references",
                }
            },
            "tenant_id": r[0],
            "revision": r[2],
        }

    def get(self, case_id, revision=None):
        revision = revision or self.metadata(case_id)["revision"]
        with self.engine.connect() as db:
            r = db.execute(
                text("SELECT data FROM snapshots WHERE case_id=:id AND revision=:r"),
                dict(id=case_id, r=revision),
            ).first()
        if not r:
            raise KeyError("snapshot not found")
        return CaseSnapshot.model_validate_json(r[0])

    def publish(self, snapshot, expected_revision, event="updated", connection=None):
        snapshot.seal()
        with self.engine.begin() if connection is None else nullcontext(connection) as db:
            changed = db.execute(
                text("UPDATE cases SET revision=:new WHERE case_id=:id AND revision=:old"),
                dict(new=snapshot.revision, id=snapshot.case_id, old=expected_revision),
            ).rowcount
            if changed != 1:
                raise ConflictError("stale_revision")
            db.execute(
                text("INSERT INTO snapshots VALUES(:id,:r,:digest,:data)"),
                dict(
                    id=snapshot.case_id,
                    r=snapshot.revision,
                    digest=snapshot.digest,
                    data=snapshot.model_dump_json(),
                ),
            )
            db.execute(
                text(
                    "INSERT INTO audit_events(case_id,revision,event,at) VALUES(:id,:r,:event,:at)"
                ),
                dict(id=snapshot.case_id, r=snapshot.revision, event=event, at=now()),
            )
            if event in {
                "artifact_added",
                "claim_corrected",
                "request_unavailable",
                "request_fulfilled",
                "victim_payment_decision",
                "feed_update_received",
                "bank_feed_received",
                "local_replay_clock",
            } or event.startswith("bank_imported:"):
                db.execute(
                    text(
                        "INSERT OR IGNORE INTO jobs(job_id,case_id,revision,status,error,priority) "
                        "VALUES(:j,:c,:r,'queued',NULL,max(:priority,coalesce("
                        "(SELECT max(priority) FROM jobs WHERE case_id=:c "
                        "AND status IN ('queued','running')),0)))"
                    ),
                    {
                        "j": "JOB-" + uuid.uuid4().hex[:12],
                        "c": snapshot.case_id,
                        "r": snapshot.revision,
                        "priority": 0 if event.startswith("bank_") else 10,
                    },
                )
        return snapshot

    def list_cases(self, tenant="demo"):
        with self.engine.connect() as db:
            return [
                dict(r._mapping)
                for r in db.execute(
                    text("SELECT case_id,revision FROM cases WHERE tenant_id=:t ORDER BY case_id"),
                    dict(t=tenant),
                )
            ]

    def cases_for_accounts(self, tenant, accounts):
        if not accounts:
            return []
        params = {"tenant": tenant}
        keys = []
        for i, account in enumerate(sorted(accounts)):
            key = "a" + str(i)
            keys.append(":" + key)
            params[key] = account
        with self.engine.connect() as db:
            return [
                r[0]
                for r in db.execute(
                    text(
                        "SELECT case_id FROM cases WHERE tenant_id=:tenant AND "
                        "json_extract(metadata,'$.customer_account') IN (" + ",".join(keys) + ")"
                    ),
                    params,
                )
            ]
