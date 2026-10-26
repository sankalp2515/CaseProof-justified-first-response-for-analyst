"""Transaction-scoped synthetic urgent referrals, independent of full-packet readiness."""

import json
import uuid

from sqlalchemy import text

from caseproof.adapters.sqlite_casestore import ConflictError
from caseproof.domain.contracts import hash_json, now


def initialise(store):
    with store.engine.begin() as db:
        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS urgent_approvals(id TEXT PRIMARY KEY,"
                "case_id TEXT,revision INTEGER,data TEXT,UNIQUE(case_id,revision))"
            )
        )
        db.execute(
            text("CREATE TABLE IF NOT EXISTS urgent_deliveries(id TEXT PRIMARY KEY,data TEXT)")
        )
        for table in ("urgent_approvals", "urgent_deliveries"):
            for action in ("UPDATE", "DELETE"):
                db.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action.lower()} "
                        f"BEFORE {action} ON {table} "
                        "BEGIN SELECT RAISE(ABORT,'immutable urgent action'); END"
                    )
                )
            db.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_insert "
                    f"BEFORE INSERT ON {table} "
                    f"WHEN EXISTS(SELECT 1 FROM {table} WHERE id=NEW.id) "
                    "BEGIN SELECT RAISE(ABORT,'immutable urgent action'); END"
                )
            )


def describe(snapshot):
    conflicts = any(c.materiality and c.evidence_state == "conflicted" for c in snapshot.claims)
    pending_evidence = any(
        not any(s.artifact_id == a.artifact_id for s in snapshot.segments)
        for a in snapshot.artifacts
    )
    eligible = bool(snapshot.ledger_matches) and not conflicts and not pending_evidence
    return {
        "eligible": eligible,
        "transaction_ids": [m.txn_id for m in snapshot.ledger_matches],
        "reason": "Identified disputed bank debit; narrative and downstream trail are separate."
        if eligible
        else "Identify a disputed bank debit; resolve conflicts and unprocessed evidence.",
    }


def approve(o, cid, actor, revision, digest, reason):
    initialise(o.store)
    if (
        actor.role not in {"reviewer", "admin"}
        or o.store.metadata(cid)["tenant_id"] != actor.tenant_id
    ):
        raise PermissionError("authorised reviewer required")
    snapshot = o.store.get(cid)
    if snapshot.revision != revision or snapshot.digest != digest:
        raise ConflictError("stale_referral")
    if not reason.strip() or len(reason) > 2000 or not describe(snapshot)["eligible"]:
        raise ValueError("referral requirements pending")
    payload = {
        "synthetic": True,
        "action": "urgent_referral",
        "approval_id": "URG-" + uuid.uuid4().hex[:12],
        "case_id": cid,
        "revision": revision,
        "digest": digest,
        "reason": reason,
        "reviewer": actor.model_dump(),
        "at": now(),
        "transactions": [m.model_dump() for m in snapshot.ledger_matches],
        "limitations": "Receipt acknowledgement only; no hold, refund or official submission.",
    }
    with o.store.engine.begin() as db:
        if (
            db.execute(
                text("UPDATE cases SET revision=revision WHERE case_id=:c AND revision=:r"),
                {"c": cid, "r": revision},
            ).rowcount
            != 1
        ):
            raise ConflictError("stale_referral")
        old = db.execute(
            text("SELECT data FROM urgent_approvals WHERE case_id=:c AND revision=:r"),
            {"c": cid, "r": revision},
        ).first()
        if old:
            existing = json.loads(old[0])
            if (
                existing["digest"] != digest
                or existing["reason"] != reason
                or existing["reviewer"] != actor.model_dump()
            ):
                raise ConflictError("immutable_referral")
            return existing
        db.execute(
            text("INSERT INTO urgent_approvals VALUES(:id,:c,:r,:d)"),
            {"id": payload["approval_id"], "c": cid, "r": revision, "d": json.dumps(payload)},
        )
        db.execute(
            text(
                "INSERT INTO audit_events(case_id,revision,event,at) "
                "VALUES(:c,:r,'urgent_referral_approved',:at)"
            ),
            {"c": cid, "r": revision, "at": payload["at"]},
        )
    return payload


def history(store, cid):
    initialise(store)
    with store.engine.connect() as db:
        return [
            {"approval": json.loads(row[0]), "delivery": json.loads(row[1]) if row[1] else None}
            for row in db.execute(
                text(
                    "SELECT a.data,d.data FROM urgent_approvals a "
                    "LEFT JOIN urgent_deliveries d ON a.id=d.id "
                    "WHERE a.case_id=:c ORDER BY a.revision"
                ),
                {"c": cid},
            )
        ]


def send(o, cid, aid, actor):
    if (
        actor.role not in {"reviewer", "admin"}
        or o.store.metadata(cid)["tenant_id"] != actor.tenant_id
    ):
        raise PermissionError("authorised reviewer required")
    from caseproof.adapters.customer_links import CustomerLinks

    with CustomerLinks(o).lock(cid + "-urgent"):
        with o.store.engine.begin() as db:
            db.execute(text("UPDATE cases SET revision=revision WHERE case_id=:c"), {"c": cid})
            row = db.execute(
                text("SELECT data FROM urgent_approvals WHERE id=:a AND case_id=:c"),
                {"a": aid, "c": cid},
            ).first()
            if not row:
                raise KeyError("referral approval missing")
            old = db.execute(
                text("SELECT data FROM urgent_deliveries WHERE id=:a"), {"a": aid}
            ).first()
            if old:
                return json.loads(old[0])
            approved = json.loads(row[0])
            snapshot = o.store.get(cid)
            if snapshot.revision != approved["revision"] or snapshot.digest != approved["digest"]:
                raise ConflictError("stale_referral")
            if not describe(snapshot)["eligible"]:
                raise ValueError("referral requirements pending")
            key = hash_json(approved)
            db.execute(
                text(
                    "INSERT OR IGNORE INTO outbox "
                    "VALUES(:k,:c,:r,'urgent_referral',:p,'pending',NULL)"
                ),
                {"k": key, "c": cid, "r": approved["revision"], "p": json.dumps(approved)},
            )
        from caseproof.adapters.http_outbound import dispatch

        return dispatch(o, key)
