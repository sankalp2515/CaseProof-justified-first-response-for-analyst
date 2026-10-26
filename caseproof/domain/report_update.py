"""Approval-bound simulated CFCFRMS report; never a hold/release decision."""

from caseproof.domain.contracts import Approval, CaseSnapshot, hash_json
from caseproof.domain.ledger import dt


def receipt_debits(snapshot: CaseSnapshot) -> list[dict]:
    """Keep unambiguous evidence-only debits explicit when the bank has no matching row."""
    by_segment = {s.segment_id: s for s in snapshot.segments}
    known = [
        (m.resolved_fields["amount"], m.resolved_fields["txn_datetime"])
        for m in snapshot.ledger_matches
    ]
    known += [(u.amount_minor, u.ts) for u in snapshot.unreported]
    output = []
    for artifact in snapshot.artifacts:
        if artifact.kind != "receipt":
            continue
        claims = [
            c
            for c in snapshot.claims
            if c.evidence_state not in {"unresolved", "conflicted"}
            and any(
                by_segment[a].artifact_id == artifact.artifact_id
                for a in c.anchor_segment_ids
                if a in by_segment
            )
        ]

        def one(kind):
            values = {str(c.normalized_value): c.normalized_value for c in claims if c.kind == kind}
            return next(iter(values.values())) if len(values) == 1 else None

        amount, timestamp = one("amount"), one("txn_datetime")
        if not isinstance(amount, int) or not isinstance(timestamp, str) or "T" not in timestamp:
            continue
        if any(
            amount == value and abs((dt(timestamp) - dt(time)).total_seconds()) <= 600
            for value, time in known
        ):
            continue
        output.append(
            {
                "txn_id": "EVIDENCE-" + hash_json([snapshot.case_id, artifact.artifact_id])[:12],
                "amount_minor": amount,
                "reference": one("transaction_reference"),
                "beneficiary": one("payee_vpa"),
                "ts": timestamp,
                "confirmation": "evidence_only_unmatched",
                "sources": sorted(
                    {
                        "claim:" + c.claim_id
                        for c in claims
                        if c.kind
                        in {"amount", "txn_datetime", "transaction_reference", "payee_vpa"}
                    }
                ),
            }
        )
    merged: dict[tuple, dict] = {}
    for debit in output:
        identity = (
            debit["amount_minor"],
            dt(debit["ts"]),
            debit["reference"],
            debit["beneficiary"],
        )
        if identity in merged:
            merged[identity]["sources"] = sorted(
                set(merged[identity]["sources"]) | set(debit["sources"])
            )
        else:
            merged[identity] = debit
    return list(merged.values())


def validate_trail_sources(trail: dict) -> None:
    """Reject orphan arithmetic without the hop path and source rows."""
    transfers = {t["txn_id"]: t for t in trail.get("transfers", [])}
    observations = {
        "cfcfrms_update:" + r["update_id"]: r for r in trail.get("account_observations", [])
    }
    located: dict[str, int] = {}
    for position in trail.get("positions", []):
        if not position["path"] or len(position["path"]) != len(position["sources"]):
            raise ValueError("unsourced traced amount")
        for txn_id, source in zip(position["path"], position["sources"]):
            if txn_id not in transfers or transfers[txn_id]["source"] != source:
                raise ValueError("unknown trail source")
        if position["amount_minor"] < 0:
            raise ValueError("negative traced amount")
        if position["status"] == "recoverable":
            source = position.get("observation_source")
            observation = observations.get(source)
            if not observation or observation["account"] != position["account"]:
                raise ValueError("recoverable amount has no bank observation")
            located[source] = located.get(source, 0) + position["amount_minor"]
    for source, amount in located.items():
        if amount > observations[source]["balance_minor"]:
            raise ValueError("recoverable amount exceeds reported bank balance")


def build_report_update(snapshot: CaseSnapshot, approval: Approval) -> dict:
    """Include confirmed matched debits and still-visible unreported own-ledger debits."""
    if (
        not snapshot.valid_digest()
        or snapshot.revision != approval.revision
        or snapshot.digest != approval.digest
    ):
        raise ValueError("stale report approval")
    validate_trail_sources(snapshot.trail)
    debits = {}
    for match in snapshot.ledger_matches:
        f = match.resolved_fields
        debits[match.txn_id] = {
            "txn_id": match.txn_id,
            "amount_minor": f["amount"],
            "reference": f["transaction_reference"],
            "beneficiary": f["payee_vpa"],
            "ts": f["txn_datetime"],
            "sources": ["ledger:" + match.txn_id] + ["claim:" + c for c in match.claim_ids],
        }
    for item in snapshot.unreported:
        debits[item.txn_id] = {
            "txn_id": item.txn_id,
            "amount_minor": item.amount_minor,
            "reference": item.reference,
            "beneficiary": item.payee,
            "ts": item.ts,
            "sources": ["ledger:" + item.txn_id],
            "confirmation": "not yet confirmed",
        }
    unmatched = receipt_debits(snapshot)
    for evidence_debit in unmatched:
        debits[evidence_debit["txn_id"]] = evidence_debit
    if snapshot.trail.get("positions") and not snapshot.trail.get("report_hash"):
        raise ValueError("missing computation hash")
    positions = snapshot.trail.get("positions", [])
    known_total = sum(d["amount_minor"] for d in debits.values()) - sum(
        d["amount_minor"] for d in unmatched
    )
    traced_total = sum(p["amount_minor"] for p in positions)
    if traced_total > known_total:
        raise ValueError("trail exceeds scoped debit amounts")
    not_traced = known_total - traced_total
    return {
        "kind": "cfcfrms_report_update",
        "synthetic": True,
        "case_id": snapshot.case_id,
        "approval_id": approval.approval_id,
        "revision": snapshot.revision,
        "digest": snapshot.digest,
        "debits": sorted(debits.values(), key=lambda d: (d["ts"], d["txn_id"])),
        "traced_amounts": positions,
        "unaccounted_amount_minor": sum(
            p["amount_minor"] for p in positions if p["status"] == "unaccounted"
        )
        + sum(d["amount_minor"] for d in unmatched)
        + not_traced,
        "unaccounted_sources": sorted(
            {s for p in positions if p["status"] == "unaccounted" for s in p["sources"]}
            | {s for d in unmatched for s in d["sources"]}
            | {s for d in debits.values() for s in d["sources"] if not_traced}
        ),
        "balance_observations": snapshot.trail.get("account_observations", []),
        **(
            {"bank_verification": snapshot.trail["bank_verification"]}
            if "bank_verification" in snapshot.trail
            else {}
        ),
        "left_system_minor": sum(
            p["amount_minor"] for p in positions if p["status"] == "left_system"
        ),
        "trace_rule": "sop_v1",
        "trace_hash": snapshot.trail.get("report_hash"),
        "clock": approval.clock_at_approval.model_dump() if approval.clock_at_approval else None,
    }
