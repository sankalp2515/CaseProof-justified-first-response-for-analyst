from typing import Any

from caseproof.domain.validator import validate_claims


def apply_corrections(claims: Any, corrections: Any, segments: Any) -> Any:
    """Apply recorded analyst corrections while retaining the source claims."""
    out = [c.model_copy(deep=True) for c in claims]
    for correction in corrections:
        target = next(
            (
                c
                for c in out
                if c.claim_id == correction["claim_id"]
                and c.kind == correction["kind"]
                and set(c.anchor_segment_ids) & set(correction["anchor_segment_ids"])
            ),
            None,
        )
        if target is None:
            # Re-extraction can assign a new ID; overlay follows kind and original anchors.
            target = next(
                (
                    c
                    for c in out
                    if c.kind == correction["kind"]
                    and set(c.anchor_segment_ids) & set(correction["anchor_segment_ids"])
                ),
                None,
            )
        if target:
            target.normalized_value = correction["value"]
            target.anchor_segment_ids = correction["anchor_segment_ids"]
            target.confidence_note = "Analyst correction: " + correction["reason"]
    return validate_claims(out, segments)


def merge_conflicts(snapshot: Any, independent_claim_ids: Any = ()) -> Any:
    # A sourced followup correction explicitly supersedes an earlier reported amount.
    """Mark incompatible supported values for explicit analyst resolution."""
    by = {s.segment_id: s for s in snapshot.segments}
    stages = {a.artifact_id: a.stage for a in snapshot.artifacts}
    corrected = [
        c
        for c in snapshot.claims
        if c.kind == "amount"
        and any(
            stages[by[s].artifact_id] == "followup" and "correction" in by[s].text.casefold()
            for s in c.anchor_segment_ids
        )
    ]
    for kind in ("amount", "transaction_reference", "txn_datetime"):
        cs = [c for c in snapshot.claims if c.kind == kind and c.evidence_state != "unresolved"]
        if kind == "txn_datetime":
            cs = [c for c in cs if "T" in str(c.normalized_value)]
        if kind == "txn_datetime":
            corrected_kind = [
                c
                for c in cs
                if any(
                    stages[by[s].artifact_id] == "followup"
                    and "correction" in by[s].text.casefold()
                    for s in c.anchor_segment_ids
                )
            ]
        else:
            corrected_kind = corrected if kind == "amount" else []
        if corrected_kind:
            for c in cs:
                if (
                    c.normalized_value != corrected_kind[-1].normalized_value
                    and c.evidence_state == "reported"
                ):
                    c.evidence_state = "unresolved"
                    c.confidence_note = "Superseded by explicit customer correction"
            cs = [c for c in cs if c.evidence_state != "unresolved"]
        # Multiple receipts / additional transfers are independent, not contradictions.
        initial = [
            c
            for c in cs
            if all(stages[by[s].artifact_id] == "initial" for s in c.anchor_segment_ids)
        ]
        if len({str(c.normalized_value) for c in initial}) > 1 and not all(
            c.claim_id in independent_claim_ids for c in initial
        ):
            for c in initial:
                c.evidence_state = "conflicted"
    return snapshot.claims


def diff(a: Any, b: Any) -> Any:
    """Describe claims and case decisions changed between two revisions."""

    def values(s):
        return {c.claim_id: c.model_dump() for c in s.claims}

    av, bv = values(a), values(b)
    return {
        "from_revision": a.revision,
        "to_revision": b.revision,
        "added": [bv[k] for k in bv.keys() - av.keys()],
        "removed": [av[k] for k in av.keys() - bv.keys()],
        "changed": [
            {"before": av[k], "after": bv[k]} for k in av.keys() & bv.keys() if av[k] != bv[k]
        ],
        "readiness": {"before": a.readiness.disposition, "after": b.readiness.disposition},
        "money_trail": {"before": a.trail, "after": b.trail},
        "clock": {
            "before": a.clock.model_dump() if a.clock else None,
            "after": b.clock.model_dump() if b.clock else None,
        },
        "new_links": [
            x.model_dump()
            for x in b.linked
            if x.complaint_id not in {item_l.complaint_id for item_l in a.linked}
        ],
    }
