import uuid
from typing import Any

from sqlalchemy import text

from caseproof.adapters.sqlite_casestore import ConflictError
from caseproof.domain.contracts import Approval


def approve(
    store: Any,
    case_id: str,
    actor: Any,
    expected_revision: Any,
    digest: Any,
    disposition: Any,
    reason: str,
) -> Any:
    """Record a reviewer decision bound to the supplied revision and digest."""
    if actor.role not in ("reviewer", "admin"):
        raise PermissionError("reviewer role required")
    if not reason.strip():
        raise ValueError("review reason required")
    s = store.get(case_id)
    if s.revision != expected_revision or s.digest != digest or not s.valid_digest():
        raise ConflictError("stale_approval")
    if store.metadata(case_id)["tenant_id"] != actor.tenant_id:
        raise PermissionError("tenant mismatch")
    target = {
        "COMPLETE_HANDOFF": "COMPLETE_CANDIDATE",
        "ESCALATE_WITH_GAPS": "ESCALATE_CANDIDATE",
    }.get(disposition)
    if s.readiness.disposition != target:
        raise ValueError("disposition inconsistent with readiness")
    from caseproof.domain.clock import current_clock
    from caseproof.domain.freshness import require_fresh_handoff

    require_fresh_handoff(s, require_coverage=disposition == "COMPLETE_HANDOFF")

    approval_clock = s.clock if s.clock and s.clock.replay else current_clock(s)
    a = Approval(
        clock_at_approval=approval_clock,
        approval_id="APP-" + uuid.uuid4().hex[:12],
        case_id=case_id,
        revision=s.revision,
        digest=digest,
        disposition=disposition,
        reviewer=actor,
        reason=reason,
    )
    if getattr(store, "cloud", False):
        return store.record_approval(a)
    with store.engine.begin() as db:
        if (
            db.execute(
                text("UPDATE cases SET revision=revision WHERE case_id=:id AND revision=:r"),
                dict(id=case_id, r=expected_revision),
            ).rowcount
            != 1
        ):
            raise ConflictError("stale_approval")
        prior = db.execute(
            text("SELECT data FROM approvals WHERE case_id=:id AND revision=:r"),
            dict(id=case_id, r=s.revision),
        ).first()
        if prior:
            existing = Approval.model_validate_json(prior[0])
            if (
                existing.digest == digest
                and existing.disposition == disposition
                and existing.reason == reason
                and existing.reviewer == actor
            ):
                return existing
            raise ConflictError("immutable_approval_requires_new_revision")
        db.execute(
            text("INSERT INTO approvals VALUES(:id,:r,:data)"),
            dict(id=case_id, r=s.revision, data=a.model_dump_json()),
        )
        db.execute(
            text("INSERT INTO approval_history VALUES(:aid,:id,:r,:data)"),
            dict(aid=a.approval_id, id=case_id, r=s.revision, data=a.model_dump_json()),
        )
        db.execute(
            text(
                "INSERT INTO audit_events(case_id,revision,event,at) VALUES(:id,:r,'approved',:at)"
            ),
            dict(id=case_id, r=s.revision, at=a.at),
        )
    return a


def approved_snapshot(store: Any, case_id: str) -> Any:
    """Return the exact approved snapshot or reject a stale approval."""
    s = store.get(case_id)
    if getattr(store, "cloud", False):
        a = store.approval(case_id, s.revision)
        if not a:
            raise ConflictError("approval_required_or_stale")
        if a.digest != s.digest or not s.valid_digest():
            raise ConflictError("approval_digest_mismatch")
        return s, a
    with store.engine.connect() as db:
        r = db.execute(
            text("SELECT data FROM approvals WHERE case_id=:id AND revision=:r"),
            dict(id=case_id, r=s.revision),
        ).first()
    if not r:
        raise ConflictError("approval_required_or_stale")
    a = Approval.model_validate_json(r[0])
    if a.digest != s.digest or not s.valid_digest():
        raise ConflictError("approval_digest_mismatch")
    return s, a
