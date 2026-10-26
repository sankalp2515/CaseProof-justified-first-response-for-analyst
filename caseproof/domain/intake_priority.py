"""Provisional server priority from owned bank selections, before OCR/AI completes."""

from caseproof.domain.clock import clock_state
from caseproof.domain.ledger import dt


def record_intake_priority(o, cid, selected):
    if not selected:
        return
    # One owned bank debit contributes once even if a client repeats its ID.
    selected = list({row["txn_id"]: row for row in selected}.values())
    snapshot = o.store.get(cid)
    if snapshot.clock or snapshot.segments:
        return
    rows = sorted(
        [
            {"txn_id": row["txn_id"], "ts": row["ts"], "basis": "bank_selection_pending_assessment"}
            for row in selected
        ],
        key=lambda row: dt(row["ts"]),
    )
    prior = snapshot.revision
    snapshot.revision += 1
    snapshot.clock = clock_state(rows[0]["ts"], debits=rows)
    snapshot.trail["intake_debit_times"] = rows
    snapshot.trail["intake_selected_amount_minor"] = sum(row["amount_minor"] for row in selected)
    o.store.publish(snapshot, prior, "bank_selection_priority_recorded")
