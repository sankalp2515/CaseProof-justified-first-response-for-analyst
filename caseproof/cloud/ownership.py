from caseproof.adapters.firestore_casestore import identity
from caseproof.adapters.sqlite_casestore import ConflictError
from caseproof.domain.contracts import now


def read(store, cid, delivered=False):
    case = store.documents.get(store.case_path(cid))
    if not case:
        raise KeyError("case not found")
    return case.get("work") or {
        "version": 0,
        "owner": "fraud_analyst",
        "state": "awaiting_external" if delivered else "open",
        "next_action": "Track receiving institution outcome; receipt is not recovery or closure."
        if delivered
        else "Review evidence and the recommended next action.",
        "due_at": None,
    }


def assign(store, cid, actor, body):
    if actor.role not in {"analyst", "admin"}:
        raise PermissionError("authorised analyst required")

    def commit(tx):
        case = tx.get(store.case_path(cid))
        if not case or case["tenant_id"] != actor.tenant_id:
            raise PermissionError("tenant mismatch")
        if case["revision"] != body.expected_revision:
            raise ConflictError("stale_revision")
        if case.get("work", {}).get("version", 0) != body.expected_version:
            raise ConflictError("stale_assignment")
        record = {
            "version": body.expected_version + 1,
            "owner": body.owner.strip(),
            "state": body.state,
            "next_action": body.next_action.strip(),
            "due_at": body.due_at,
            "reason": body.reason.strip(),
            "actor": actor.model_dump(),
            "at": now(),
        }
        if not all(record[k] for k in ("owner", "next_action", "reason")):
            raise ValueError("owner, action and reason required")
        case["work"] = record
        tx.set(store.case_path(cid), case)
        tx.set("work_history/" + identity(cid, record["version"]), record, create=True)
        store.audit_write(tx, case, "followup_assigned")
        return record

    return store.documents.transact(commit)
