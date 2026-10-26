"""Append-only operational assignment; does not change financial approval scope."""

import json

from sqlalchemy import text

from caseproof.adapters.sqlite_casestore import ConflictError
from caseproof.domain.contracts import now


def initialise(store):
    if getattr(store, "cloud", False):
        return
    with store.engine.begin() as db:
        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS case_work "
                "(case_id TEXT,version INTEGER,data TEXT,PRIMARY KEY(case_id,version))"
            )
        )
        for operation in ("UPDATE", "DELETE"):
            db.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS work_{operation.lower()} BEFORE "
                    f"{operation} ON case_work BEGIN "
                    "SELECT RAISE(ABORT,'immutable work history'); END"
                )
            )
        db.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS work_no_replace BEFORE INSERT ON case_work "
                "WHEN EXISTS(SELECT 1 FROM case_work WHERE case_id=NEW.case_id "
                "AND version=NEW.version) BEGIN "
                "SELECT RAISE(ABORT,'immutable work history'); END"
            )
        )


def read(store, cid, delivered=False):
    if getattr(store, "cloud", False):
        from caseproof.cloud.ownership import read as cloud_read

        return cloud_read(store, cid, delivered)
    with store.engine.connect() as db:
        row = db.execute(
            text("SELECT data FROM case_work WHERE case_id=:c ORDER BY version DESC LIMIT 1"),
            {"c": cid},
        ).scalar()
    return (
        json.loads(row)
        if row
        else {
            "version": 0,
            "owner": "fraud_analyst",
            "state": "awaiting_external" if delivered else "open",
            "next_action": (
                "Track receiving institution outcome; receipt is not recovery or closure."
            )
            if delivered
            else "Review evidence and the recommended next action.",
            "due_at": None,
        }
    )


def assign(store, cid, actor, body):
    if getattr(store, "cloud", False):
        from caseproof.cloud.ownership import assign as cloud_assign

        return cloud_assign(store, cid, actor, body)
    initialise(store)
    if (
        actor.role not in {"analyst", "admin"}
        or store.metadata(cid)["tenant_id"] != actor.tenant_id
    ):
        raise PermissionError("authorised analyst required")
    with store.engine.begin() as db:
        if (
            db.execute(
                text("UPDATE cases SET revision=revision WHERE case_id=:c AND revision=:r"),
                {"c": cid, "r": body.expected_revision},
            ).rowcount
            != 1
        ):
            raise ConflictError("stale_revision")
        version = db.execute(
            text("SELECT coalesce(max(version),0) FROM case_work WHERE case_id=:c"), {"c": cid}
        ).scalar()
        if version != body.expected_version:
            raise ConflictError("stale_assignment")
        record = {
            "version": version + 1,
            "owner": body.owner.strip(),
            "state": body.state,
            "next_action": body.next_action.strip(),
            "due_at": body.due_at,
            "reason": body.reason.strip(),
            "actor": actor.model_dump(),
            "at": now(),
        }
        if not record["owner"] or not record["next_action"] or not record["reason"]:
            raise ValueError("owner, action and reason required")
        db.execute(
            text("INSERT INTO case_work VALUES(:c,:v,:d)"),
            {"c": cid, "v": record["version"], "d": json.dumps(record)},
        )
        db.execute(
            text(
                "INSERT INTO audit_events(case_id,revision,event,at) "
                "VALUES(:c,:r,'followup_assigned',:at)"
            ),
            {"c": cid, "r": body.expected_revision, "at": record["at"]},
        )
    return record
