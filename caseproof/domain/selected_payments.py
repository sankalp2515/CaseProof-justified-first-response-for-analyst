"""Compare selected authoritative debits with receipt claims without replacing evidence."""

from caseproof.domain.ledger import dt, normalized


def independent_receipt_claims(snapshot, transactions):
    """Identify receipts independently corroborated without inventing missing OCR time."""
    by_segment = {s.segment_id: s for s in snapshot.segments}
    independent = set()
    for artifact in snapshot.artifacts:
        if artifact.kind != "receipt":
            continue
        claims = [
            c
            for c in snapshot.claims
            if c.evidence_state not in {"unresolved", "conflicted"}
            and c.anchor_segment_ids
            and all(
                a in by_segment and by_segment[a].artifact_id == artifact.artifact_id
                for a in c.anchor_segment_ids
            )
        ]
        refs = {normalized(c.normalized_value) for c in claims if c.kind == "transaction_reference"}
        reference_rows = [
            t
            for t in transactions
            if t["direction"] == "debit" and normalized(t["reference"]) in refs
        ]
        if len(refs) == 1 and len(reference_rows) == 1:
            independent.update(c.claim_id for c in claims if c.kind == "transaction_reference")
        amounts = {c.normalized_value for c in claims if c.kind == "amount"}
        if len(refs) != 1 or len(amounts) != 1:
            continue
        targets = [
            t
            for t in transactions
            if t["direction"] == "debit"
            and normalized(t["reference"]) in refs
            and t["amount_minor"] in amounts
        ]
        if len(targets) != 1:
            continue
        target = targets[0]
        if any(
            c.kind == "payee_vpa" and normalized(c.normalized_value) != normalized(target["payee"])
            for c in claims
        ):
            continue
        dates = [str(c.normalized_value) for c in claims if c.kind == "txn_datetime"]
        if any(
            (
                abs((dt(at) - dt(target["ts"])).total_seconds()) > 600
                if "T" in at
                else dt(at).date() != dt(target["ts"]).date()
            )
            for at in dates
        ):
            continue
        independent.update(c.claim_id for c in claims)
    # This suppresses a false cross-receipt contradiction only. Ledger matching,
    # selected disputes, per-receipt conflicts and readiness remain separate gates.
    return independent


def flag_conflicts(snapshot, transactions, selected):
    by_segment = {s.segment_id: s for s in snapshot.segments}
    for artifact in snapshot.artifacts:
        if artifact.kind != "receipt":
            continue
        claims = [
            c
            for c in snapshot.claims
            if any(
                a in by_segment and by_segment[a].artifact_id == artifact.artifact_id
                for a in c.anchor_segment_ids
            )
        ]
        references = {
            normalized(c.normalized_value) for c in claims if c.kind == "transaction_reference"
        }
        targets = [
            t
            for t in transactions
            if t["txn_id"] in selected and normalized(t["reference"]) in references
        ]
        if not references:
            payees = {normalized(c.normalized_value) for c in claims if c.kind == "payee_vpa"}
            times = [
                str(c.normalized_value)
                for c in claims
                if c.kind == "txn_datetime" and "T" in str(c.normalized_value)
            ]
            amounts = {c.normalized_value for c in claims if c.kind == "amount"}
            if any(
                t["txn_id"] not in selected
                and t["amount_minor"] in amounts
                and normalized(t["payee"]) in payees
                and any(abs((dt(at) - dt(t["ts"])).total_seconds()) <= 600 for at in times)
                for t in transactions
            ):
                # An independently corroborated second payment is additional evidence,
                # not a contradiction of the customer's selected first payment.
                continue
            # Cropped references are supported. A matching payee AND transaction
            # time can associate the receipt, but an amount alone cannot.
            targets = [
                t
                for t in transactions
                if t["txn_id"] in selected
                and normalized(t["payee"]) in payees
                and any(abs((dt(at) - dt(t["ts"])).total_seconds()) <= 600 for at in times)
            ]
        if not targets:
            for claim in claims:
                if claim.kind == "amount" and claim.evidence_state != "unresolved":
                    claim.evidence_state = "unresolved"
                    claim.confidence_note = (
                        "receipt_unassociated: identify the payment described by this receipt; "
                        "do not assume it corroborates a selected bank debit."
                    )
            continue
        for c in claims:
            if c.evidence_state == "unresolved":
                continue
            conflicting = c.kind == "amount" and c.normalized_value not in {
                t["amount_minor"] for t in targets
            }
            if c.kind == "payee_vpa":
                conflicting = normalized(c.normalized_value) not in {
                    normalized(t["payee"]) for t in targets
                }
            if c.kind == "txn_datetime" and "T" in str(c.normalized_value):
                conflicting = all(
                    abs((dt(str(c.normalized_value)) - dt(t["ts"])).total_seconds()) > 600
                    for t in targets
                )
            if conflicting:
                c.evidence_state = "conflicted"
                c.confidence_note = "Receipt conflicts with the associated selected bank payment."
