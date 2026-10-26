from typing import Any

from caseproof.adapters.sqlite_casestore import ConflictError
from caseproof.domain.evidence import apply_corrections
from caseproof.domain.requests import blocked


def bank_unavailable(o, case_id, reason, expected_revision):
    """Record an internal verification failure; never fabricate a victim response."""
    from caseproof.domain.contracts import EvidenceRequest
    from caseproof.pipeline.investigate import assess

    snap = o.store.get(case_id)
    if snap.revision != expected_revision:
        raise ConflictError("stale_revision")
    gaps = [g for g in snap.gaps if g.required_fact in {"bank_verified", "ledger_coverage"}]
    if not gaps or not reason.strip() or len(reason) > 2000 or not snap.artifacts:
        raise ValueError("a current bank verification gap and bounded reason are required")
    snap.requests.append(
        EvidenceRequest(
            request_id=f"INTERNAL-BANK-{snap.revision}",
            catalogue_id="internal_bank_verification",
            state="unavailable",
            reason=reason.strip(),
            resolves_gap_ids=[g.gap_id for g in gaps],
            explanation={
                "can_settle": [g.required_fact for g in gaps],
                "cannot_prove": ["Bank verification remains unavailable; internal escalation only"],
            },
        )
    )
    assess(o, snap)
    old = snap.revision
    snap.revision += 1
    return o.store.publish(snap, old, "bank_verification_unavailable")


def request_state(
    o: Any,
    case_id: str,
    request_id: str,
    state: Any,
    reason: str = "",
    expected_revision: Any = None,
) -> Any:
    """Publish a request-state change as a new immutable case revision."""
    snap = o.store.get(case_id)
    old = snap.revision
    if expected_revision is not None and expected_revision != old:
        raise ConflictError("stale_revision")
    req = next((r for r in snap.requests if r.request_id == request_id), None)
    if not req:
        raise KeyError("request not found")
    transitions = {
        "proposed": {"accepted", "skipped", "unavailable"},
        "accepted": {"fulfilled", "unavailable", "skipped"},
    }
    if state not in transitions.get(req.state, set()):
        raise ValueError("invalid request transition")
    if req.state in ("blocked", "suppressed") or blocked(req.reason):
        raise ValueError("unsafe or suppressed request")
    if state in ("unavailable", "skipped") and not reason.strip():
        raise ValueError("reason required")
    req.state = state
    if reason:
        req.reason = reason
    snap.revision += 1
    snap.readiness.disposition = "REVIEW_REQUIRED"
    return o.store.publish(snap, old, "request_" + state)


def correct(
    o: Any, case_id: str, claim_id: Any, value: Any, reason: str, expected_revision: Any
) -> Any:
    """Record an analyst correction with its reason and original claim preserved."""
    snap = o.store.get(case_id)
    old = snap.revision
    if old != expected_revision:
        raise ConflictError("stale_revision")
    if not reason.strip():
        raise ValueError("correction reason required")
    target = next((c for c in snap.claims if c.claim_id == claim_id), None)
    if not target:
        raise KeyError("claim not found")
    correction = dict(
        claim_id=claim_id,
        kind=target.kind,
        value=value,
        reason=reason,
        anchor_segment_ids=target.anchor_segment_ids,
    )
    snap.corrections.append(correction)
    snap.claims = apply_corrections(snap.claims, snap.corrections, snap.segments)
    snap.revision += 1
    snap.readiness.disposition = "REVIEW_REQUIRED"
    return o.store.publish(snap, old, "claim_corrected")
