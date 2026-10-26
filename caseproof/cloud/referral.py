import uuid

from caseproof.adapters.firestore_casestore import identity
from caseproof.adapters.sqlite_casestore import ConflictError
from caseproof.domain.contracts import hash_json, now
from caseproof.domain.referral import describe


def approve(o, cid, actor, revision, digest, reason):
    if actor.role not in {"reviewer", "admin"}:
        raise PermissionError("reviewer required")
    snap = o.store.get(cid)
    if snap.revision != revision or snap.digest != digest or not snap.valid_digest():
        raise ConflictError("stale_referral")
    if not reason.strip() or len(reason) > 2000 or not describe(snap)["eligible"]:
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
        "transactions": [m.model_dump() for m in snap.ledger_matches],
        "limitations": "Receipt acknowledgement only; no hold, refund or official submission.",
    }

    def commit(tx):
        case = tx.get(o.store.case_path(cid))
        if case["tenant_id"] != actor.tenant_id:
            raise PermissionError("tenant mismatch")
        if case["revision"] != revision or case["digest"] != digest:
            raise ConflictError("stale_referral")
        path = "urgent_approvals/" + identity(cid, revision)
        prior = tx.get(path)
        if prior:
            if any(prior[k] != payload[k] for k in ("digest", "reason", "reviewer")):
                raise ConflictError("immutable_referral")
            return prior
        tx.set(path, payload, create=True)
        o.store.audit_write(tx, case, "urgent_referral_approved")
        return payload

    return o.store.documents.transact(commit)


def send(o, cid, aid, actor):
    if actor.role not in {"reviewer", "admin"}:
        raise PermissionError("reviewer required")

    def commit(tx):
        case = tx.get(o.store.case_path(cid))
        if case["tenant_id"] != actor.tenant_id:
            raise PermissionError("tenant mismatch")
        payload = tx.get("urgent_approvals/" + identity(cid, case["revision"]))
        if not payload or payload["approval_id"] != aid or payload["digest"] != case["digest"]:
            raise ConflictError("stale_referral")
        key = hash_json(payload)
        if not tx.get("outbox/" + key):
            tx.set(
                "outbox/" + key,
                {
                    "key": key,
                    "case_id": cid,
                    "revision": case["revision"],
                    "digest": case["digest"],
                    "kind": "urgent_referral",
                    "payload": payload,
                    "status": "pending",
                    "response": None,
                    "attempts": 0,
                    "lease_token": None,
                    "lease_until": 0,
                },
                create=True,
            )
            o.store.intent_write(tx, key, "outbound", key)
        return {"queued": True, "delivery_id": key}

    return o.store.documents.transact(commit)


def history(store, cid):
    rows = store.documents.query("urgent_approvals", [("case_id", cid)], limit=100)
    result = []
    for row in sorted(rows, key=lambda r: r["revision"]):
        delivery = store.documents.get("outbox/" + hash_json(row))
        result.append({"approval": row, "delivery": delivery.get("response") if delivery else None})
    return result
