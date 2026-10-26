import re
from typing import Any

from caseproof.domain.contracts import PacketManifest, hash_json
from caseproof.domain.validator import STRICT, supported, validate_claims


def validate_markers(summary: Any, sources: Any) -> None:
    """Reject narrative citations that do not identify stored evidence."""
    if any(m not in sources for m in re.findall(r"\[(?:E|L)\d+\]", summary)):
        raise ValueError("unknown_summary_marker")


def build_packet(snapshot: Any, approval: Any, summary: Any = None) -> Any:
    """Build a sourced handoff packet from the exact approved revision."""
    if (
        not snapshot.valid_digest()
        or snapshot.digest != approval.digest
        or snapshot.revision != approval.revision
    ):
        raise ValueError("unapproved snapshot")
    validated = validate_claims(snapshot.claims, snapshot.segments)
    by = {s.segment_id: s for s in snapshot.segments}
    claims = []
    markers = {s.segment_id: f"[E{i + 1}]" for i, s in enumerate(snapshot.segments)}
    for c in validated:
        if c.evidence_state in ("unresolved", "conflicted") or c.kind == "embedded_instruction":
            continue
        if c.kind in STRICT and not supported(c, by):
            raise ValueError("unsupported_packet_claim")
        sources = [
            {
                **by[s].model_dump(),
                "marker": markers[s],
                "anchor_label": (
                    "model OCR" if by[s].box_2d is not None else "approximate model OCR"
                )
                if by[s].source == "model_ocr"
                else "exact text",
                "mode": "mock"
                if (by[s].ocr_model_id or "").startswith("mock")
                else "local"
                if (by[s].ocr_model_id or "").startswith("tesseract")
                else "observed",
            }
            for s in c.anchor_segment_ids
        ]
        claims.append({**c.model_dump(), "sources": sources})
    transactions = [
        {**m.model_dump(), "marker": f"[L{i + 1}]"} for i, m in enumerate(snapshot.ledger_matches)
    ]
    allowed = set(markers.values()) | {t["marker"] for t in transactions}
    summary = summary or (
        "Synthetic complaint assessed for "
        + approval.disposition
        + ". "
        + " ".join(t["marker"] for t in transactions)
        + " Transaction records are synthetic; caller identity remains unverified."
    )
    validate_markers(summary, allowed)
    from caseproof.domain.brief import build_brief
    from caseproof.domain.report_update import build_report_update

    return PacketManifest(
        investigation_brief=build_brief(snapshot, approval),
        facts=snapshot.facts,
        report_update=build_report_update(snapshot, approval),
        packet_id="SYNTH-PACKET-"
        + hash_json(
            {
                "case_id": snapshot.case_id,
                "revision": snapshot.revision,
                "digest": snapshot.digest,
                "approval_id": approval.approval_id,
            }
        )[:16],
        approval_id=approval.approval_id,
        revision=snapshot.revision,
        summary=summary,
        claims_with_sources=claims,
        transactions=transactions,
        linked=[item_l.model_dump() for item_l in snapshot.linked],
        unresolved=[g.model_dump() for g in snapshot.gaps if g.resolvable_by != "ledger"],
        request_history=[r.model_dump() for r in snapshot.requests],
        audit={
            "clock_at_approval": approval.clock_at_approval.model_dump()
            if approval.clock_at_approval
            else None,
            "facts": [f.model_dump() for f in snapshot.facts],
            "synthetic": True,
            "digest": snapshot.digest,
            "approval": approval.model_dump(),
            "run_meta": [r.model_dump() for r in snapshot.run_meta],
            "policy_version": snapshot.readiness.policy_version,
            "mode": "mock"
            if not snapshot.run_meta or any(r.mode == "mock" for r in snapshot.run_meta)
            else "local"
            if all(r.mode == "local" for r in snapshot.run_meta)
            else "live_or_cache",
        },
    )
