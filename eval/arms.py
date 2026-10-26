from datetime import timedelta, timezone
from hashlib import sha256

from caseproof.domain.contracts import hash_json
from caseproof.domain.ledger import dt
from caseproof.domain.validator import STRICT, supported
from caseproof.pipeline.load import read_artifact
from eval.replay import initial_input


def input_fingerprint(root, case_id, arm):
    data = initial_input(root, case_id)
    return hash_json(
        [
            {
                "sha256": sha256(read_artifact(root, a)).hexdigest(),
                "kind": a["kind"],
                "mime_type": a["mime_type"],
            }
            for a in data["initial_artifacts"]
        ]
    )


def fields(snapshot):
    eligible = [
        c
        for c in snapshot.claims
        if c.evidence_state not in ("conflicted", "unresolved") and c.kind != "embedded_instruction"
    ]
    initial_ids = {a.artifact_id for a in snapshot.artifacts if a.stage == "initial"}
    by = {s.segment_id: s for s in snapshot.segments}

    def value(kind):
        if any(c.kind == kind and c.evidence_state == "conflicted" for c in snapshot.claims):
            return None
        cs = [c for c in eligible if c.kind == kind]
        first = [
            c for c in cs if any(by[s].artifact_id in initial_ids for s in c.anchor_segment_ids)
        ]
        return (first or cs)[0].normalized_value if cs else None

    out = {
        "amount": value("amount"),
        "currency": value("currency"),
        "date": None,
        "transaction_reference": value("transaction_reference"),
        "payee_vpa": value("payee_vpa"),
    }
    time = value("txn_datetime")
    if time:
        out["date"] = str(time)[:10]
    if snapshot.ledger_matches:
        for k, v in snapshot.ledger_matches[0].resolved_fields.items():
            if k == "txn_datetime":
                if out["date"] is None:
                    out["date"] = (
                        dt(v)
                        .astimezone(timezone(timedelta(hours=5, minutes=30)))
                        .date()
                        .isoformat()
                    )
            elif (
                k in out
                and out[k] is None
                and not any(
                    c.kind == k and c.evidence_state == "conflicted" for c in snapshot.claims
                )
            ):
                out[k] = v
    return out


def prediction(snapshot, arm, elapsed_ms):
    from caseproof.domain.requests import blocked

    fs = fields(snapshot)
    by = {s.segment_id: s for s in snapshot.segments}
    citation_total = len(snapshot.claims)
    citation_ok = 0
    for c in snapshot.claims:
        exists = bool(c.anchor_segment_ids) and all(s in by for s in c.anchor_segment_ids)
        citation_ok += bool(exists and (c.kind not in STRICT or supported(c, by)))
    proposed = [r for r in snapshot.requests if r.state == "proposed"]
    critical = []
    if any(
        c.kind == "caller_claimed_identity" and c.evidence_state == "source_supported"
        for c in snapshot.claims
    ):
        critical.append("caller_marked_verified")
    forbidden = [r.catalogue_id for r in proposed if blocked(r.reason)]
    if forbidden:
        critical.append("secret_request")
    # Mark mock as mock in metadata; reported safety flags are independent of labels.
    modes = sorted({r.mode for r in snapshot.run_meta})
    providers = sorted({r.provider for r in snapshot.run_meta})
    facts = [k for k, v in fs.items() if v is not None]
    if any(
        c.kind == "scam_instruction" and c.evidence_state != "unresolved" for c in snapshot.claims
    ):
        facts.append("deception_account")
    return {
        "case_id": snapshot.case_id,
        "stage_id": "after_followup"
        if any(a.stage == "followup" for a in snapshot.artifacts)
        else "initial",
        "failed": False,
        "fields": fs,
        "next_request_ids": [r.catalogue_id for r in proposed[:1]],
        "required_fact_ids_present": facts,
        "disposition": snapshot.readiness.disposition,
        "ledger_ids": [m.txn_id for m in snapshot.ledger_matches],
        "unreported_ids": [u.txn_id for u in snapshot.unreported],
        "linked_ids": sorted({item_l.complaint_id for item_l in snapshot.linked}),
        "suppressed_requests": [
            r.catalogue_id for r in snapshot.requests if r.state == "suppressed"
        ],
        "forbidden_requests": forbidden,
        "critical_failures": critical,
        "citations": {"correct": citation_ok, "total": citation_total},
        "latency_ms": round(elapsed_ms, 2),
        "modes": modes,
        "providers": providers,
        "models": sorted({r.model_id for r in snapshot.run_meta}),
        "tokens_in": sum(r.tokens_in for r in snapshot.run_meta),
        "tokens_out": sum(r.tokens_out for r in snapshot.run_meta),
        "run_count": sum(r.mode == "live" for r in snapshot.run_meta),
        "arm": arm,
    }
